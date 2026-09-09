"""Builds seed_knowledge.json: verifies every seed fact quote against the real
PDFs (grounding proof), computes pages, then writes the final seed file.

Run: uv run python scripts/build_seed.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import SEED_PATH  # noqa: E402
from app.ingest import parse_pdf  # noqa: E402
from app.textnorm import verify_quote  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "starter-datasets" / "starter-datasets"
SRC = Path(__file__).resolve().parents[1] / "seed" / "seed_source.json"

source = json.loads(SRC.read_text(encoding="utf-8"))

docs = {}
for d in source["documents"]:
    pdf = DATASETS / d["file"]
    parsed = parse_pdf(pdf, d["doc_id"], d["name"])
    docs[d["doc_id"]] = parsed
    print(f"parsed {d['doc_id']}: {parsed.num_pages} pages, {len(parsed.chunks)} chunks")

facts, failures = [], []
key_to_id = {}
for f in source["facts"]:
    parsed = docs[f["doc_id"]]
    check = verify_quote(f["quote"], parsed.pages)
    if not check.verified:
        failures.append(f["key"])
        print(f"UNVERIFIED [{f['key']}] page~{check.page} score={check.score:.2f}: {f['quote'][:70]}...")
        continue
    import hashlib

    fid = "f_" + hashlib.sha1(f"{f['doc_id']}|{check.page}|{f['claim']}".encode()).hexdigest()[:12]
    key_to_id[f["key"]] = fid
    facts.append(
        {
            "fact_id": fid,
            "doc_id": f["doc_id"],
            "claim": f["claim"],
            "value": f.get("value"),
            "unit": f.get("unit"),
            "type": f.get("type", "other"),
            "page": check.page,
            "quote": f["quote"],
            "confidence": f.get("confidence", 0.9),
            "source": "seed",
            "score": round(check.score, 3),
        }
    )
    pg = f"p{check.page}" if check.score < 1.0 else "exact"
    print(f"ok [{f['key']}] -> {fid} page {check.page} ({pg})")

rels = []
for r in source["curated_relationships"]:
    if r["a"] not in key_to_id or r["b"] not in key_to_id:
        failures.append(f"rel {r['a']}-{r['b']}")
        print(f"SKIP rel (missing fact): {r['a']} - {r['b']}")
        continue
    rels.append(
        {
            "rel_id": "r_" + hashlib.sha1(
                "|".join(sorted([key_to_id[r["a"]], key_to_id[r["b"]]])).encode()
            ).hexdigest()[:12],
            "fact_id_a": key_to_id[r["a"]],
            "fact_id_b": key_to_id[r["b"]],
            "kind": r["kind"],
            "explanation": r["explanation"],
            "source": "seed",
        }
    )

pairs = [
    [key_to_id[a], key_to_id[b]]
    for a, b in source["candidate_pairs"]
    if a in key_to_id and b in key_to_id
]

showcase = []
for s in source["showcase"]:
    a_id, b_id = key_to_id.get(s["a"]), key_to_id.get(s["b"])
    if a_id and b_id:
        showcase.append({**s, "fact_id_a": a_id, "fact_id_b": b_id})

out = {
    "documents": source["documents"],
    "facts": facts,
    "candidate_pairs": pairs,
    "curated_relationships": rels,
    "failures": source["failures"],
    "showcase": showcase,
}
SEED_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nwrote {SEED_PATH}: {len(facts)} facts, {len(rels)} relationships, "
      f"{len(pairs)} candidate pairs, {len(showcase)} showcase cases")
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
