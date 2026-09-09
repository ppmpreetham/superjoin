"""Cross-document comparison pipeline.

1. Embed fact claims locally (sentence-transformers) - cheap candidate recall.
2. Candidate pairs above a similarity threshold go to the LLM (if configured)
   for classification: corroborates | contradicts | reconciles | unrelated.
3. Without an LLM, deterministic numeric/unit heuristics classify pairs.
"""
import itertools
import re
from datetime import datetime, timezone

import numpy as np

from .config import EMBED_CANDIDATES, EMBED_MODEL, EMBED_THRESHOLD
from .llm import LLM, LLMError

COMPARE_SYSTEM = """You compare two extracted facts. Decide their relationship:
- "corroborates": same underlying fact, possibly different wording/units.
- "contradicts": genuinely conflicting claims about the same thing.
- "reconciles": appear conflicting but differ by time period, scope, units,
  definitions or source vintage - explain exactly what reconciles them.
- "unrelated": about different things.

Cite the evidence quotes in your explanation. Return JSON:
{"kind": "corroborates|contradicts|reconciles|unrelated",
 "explanation": "one to three sentences citing the quotes and reasoning"}"""

NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def parse_number(s):
    if s is None:
        return None
    m = NUM_RE.search(str(s).replace(",", ""))
    return float(m.group(0)) if m else None


def _rel_id(a, b) -> str:
    import hashlib

    lo, hi = sorted([a, b])
    return "r_" + hashlib.sha1(f"{lo}|{hi}".encode()).hexdigest()[:12]


def load_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBED_MODEL)


def candidate_pairs(facts, model):
    """Embed claims, return top candidate pairs above threshold."""
    if len(facts) < 2:
        return []
    claims = [f["claim"] for f in facts]
    emb = model.encode(claims, normalize_embeddings=True)
    emb = np.asarray(emb)
    sims = emb @ emb.T
    pairs = []
    n = len(facts)
    for i, j in itertools.combinations(range(n), 2):
        if facts[i]["doc_id"] == facts[j]["doc_id"]:
            continue
        if sims[i, j] >= EMBED_THRESHOLD:
            pairs.append((sims[i, j], facts[i], facts[j]))
    pairs.sort(key=lambda x: -x[0])
    return pairs[: EMBED_CANDIDATES * n]


def heuristic_classify(fa: dict, fb: dict):
    """Deterministic numeric comparison used when no LLM is configured."""
    va, vb = parse_number(fa.get("value")), parse_number(fb.get("value"))
    if va is None or vb is None:
        return None
    if va == 0 and vb == 0:
        return None
    diff = abs(va - vb) / max(abs(va), abs(vb), 1e-9)
    ratio = max(va, vb) / max(min(va, vb), 1e-9)
    if diff <= 0.01:
        kind = "corroborates"
        expl = (
            f"Both facts state the same value ({va:g} vs {vb:g}, within 1%); "
            f"the wording differs but the number matches."
        )
    elif diff <= 0.15:
        kind = "reconciles"
        expl = (
            f"Values differ by {diff:.0%} ({va:g} vs {vb:g}), likely due to differing "
            f"scope, period, rounding or unit definitions between the two documents."
        )
    elif ratio > 3:
        # A 3x+ scale gap is almost always a units problem (Cr vs Mn, tons vs
        # '000 tonnes), not a genuine disagreement. The heuristic classifier
        # cannot resolve units, so it says so instead of crying contradiction.
        kind = "reconciles"
        expl = (
            f"Values differ by a factor of ~{ratio:.0f} ({va:g} vs {vb:g}). "
            f"This is most likely a unit/scale mismatch (e.g. crore vs million, "
            f"tons vs thousand tonnes) rather than a genuine conflict; the "
            f"heuristic classifier cannot resolve units, so human review is needed."
        )
    else:
        kind = "contradicts"
        expl = (
            f"Values differ substantially ({va:g} vs {vb:g}, {diff:.0%} apart) with "
            f"no obvious reconciling context detected by the heuristic classifier."
        )
    return kind, expl


def compare_facts(facts, llm: LLM, conn):
    """Run comparison over candidate pairs; persist classified relationships."""
    from .store import add_failure, upsert_relationship

    model = load_model()
    pairs = candidate_pairs(facts, model)
    rels = []
    for sim, fa, fb in pairs:
        if llm.available:
            user = (
                f"Fact A (doc {fa['doc_id']}, page {fa['page']}):\n"
                f"Claim: {fa['claim']}\nEvidence quote: \"{fa['quote']}\"\n\n"
                f"Fact B (doc {fb['doc_id']}, page {fb['page']}):\n"
                f"Claim: {fb['claim']}\nEvidence quote: \"{fb['quote']}\"\n"
            )
            try:
                result = llm.complete_json(COMPARE_SYSTEM, user)
                kind = result.get("kind", "unrelated")
                expl = result.get("explanation", "")
                source = "llm"
            except (LLMError, Exception) as e:
                add_failure(conn, None, "compare_llm", f"Comparison failed: {e}")
                hc = heuristic_classify(fa, fb)
                if hc is None:
                    continue
                kind, expl = hc
                source = "heuristic"
        else:
            hc = heuristic_classify(fa, fb)
            if hc is None:
                continue
            kind, expl = hc
            source = "heuristic"

        if kind not in ("corroborates", "contradicts", "reconciles"):
            continue
        rel_id = _rel_id(fa["fact_id"], fb["fact_id"])
        # Never overwrite a human-curated (seed) relationship for this pair.
        existing = conn.execute(
            "SELECT source FROM relationships WHERE rel_id = ?", (rel_id,)
        ).fetchone()
        if existing and existing["source"] == "seed":
            continue
        rel = {
            "rel_id": rel_id,
            "fact_id_a": fa["fact_id"],
            "fact_id_b": fb["fact_id"],
            "kind": kind,
            "explanation": expl,
            "source": source,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_relationship(conn, rel)
        rels.append(rel)
    return rels
