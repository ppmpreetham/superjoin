"""Fact extraction pipeline.

Two modes:
- LLM mode: chunked extraction with forced grounding (quote + page per fact).
- Heuristic mode (no LLM configured): number-bearing sentences become facts,
  each fact is a verbatim sentence, so grounding is exact by construction.

Either way, quotes are verified against page text before storage (textnorm).
"""
import hashlib
import re
from datetime import datetime, timezone

from .config import PAGES_PER_LLM_CALL
from .llm import LLM, LLMError
from .ingest import ParsedDoc
from .textnorm import verify_quote

FACT_SYSTEM = """You are a precise information extraction engine. Extract atomic, verifiable
facts from the given document text. Rules:
1. Every fact MUST include a verbatim supporting quote from the text (exact substring).
2. Every fact MUST include the correct page number (given as [PAGE n] markers).
3. Prefer numerical, temporal, entity and relational facts (amounts, dates, names,
   percentages, counts, statuses).
4. Keep facts atomic: one claim per fact.
5. Never invent values; only extract what the text states.
6. Do not extract boilerplate, disclaimers or repeated navigation text.

Return JSON: {"facts": [{"claim": "...", "value": "...", "unit": "...",
"type": "numerical|entity|temporal|relational|other", "page": n, "quote": "...",
"confidence": 0.0-1.0}]}"""

NUM_SENTENCE = re.compile(r"[A-Za-z\u0900-\u097F][^\.\n]{0,300}[₹$€0-9][^\.\n]{0,300}")
NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _fact_id(doc_id: str, claim: str, page) -> str:
    h = hashlib.sha1(f"{doc_id}|{page}|{claim}".encode()).hexdigest()[:12]
    return f"f_{h}"


def _verify_store(fact: dict, pages: dict, doc_id: str, source: str, conn):
    """Verify a fact's quote against page text; store if grounded, else log failure."""
    quote = fact.get("quote", "")
    check = verify_quote(quote, pages)
    if not check.verified:
        from .store import add_failure

        add_failure(
            conn,
            doc_id,
            "grounding",
            f"Rejected ungrounded fact: claim={fact.get('claim')!r} "
            f"quote={quote[:80]!r} (best page {check.page}, score {check.score:.2f})",
        )
        return None
    fid = _fact_id(doc_id, fact["claim"], check.page)
    record = {
        "fact_id": fid,
        "doc_id": doc_id,
        "claim": fact["claim"],
        "value": fact.get("value"),
        "unit": fact.get("unit"),
        "type": fact.get("type", "other"),
        "page": check.page,
        "quote": quote,
        "confidence": fact.get("confidence", 0.8),
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    from .store import upsert_fact

    upsert_fact(conn, record)
    return record


def extract_heuristic(parsed: ParsedDoc, conn):
    """No-LLM fallback: verbatim number-bearing sentences as facts."""
    import sqlite3

    facts = []
    seen = set()
    for chunk in parsed.chunks:
        for m in NUM_SENTENCE.finditer(chunk.text):
            sentence = m.group(0).strip()
            key = (chunk.page, sentence)
            if key in seen or len(sentence) < 15:
                continue
            seen.add(key)
            # Derive a structured value from the sentence so the numeric
            # cross-doc classifier has something to compare.
            nums = NUM_RE.findall(sentence.replace(",", ""))
            value = nums[0] if nums else None
            fact = {
                "claim": sentence,
                "quote": sentence,
                "value": value,
                "type": "numerical",
                "page": chunk.page,
                "confidence": 0.3,
            }
            rec = _verify_store(fact, parsed.pages, parsed.doc_id, "heuristic", conn)
            if rec:
                facts.append(rec)
    return facts


def extract_llm(parsed: ParsedDoc, llm: LLM, conn):
    """LLM extraction over page-grouped chunks, then verify each fact's quote."""
    pages_sorted = sorted(parsed.pages)
    facts = []
    for i in range(0, len(pages_sorted), PAGES_PER_LLM_CALL):
        group = pages_sorted[i : i + PAGES_PER_LLM_CALL]
        text_blocks = []
        for p in group:
            t = parsed.pages[p]
            if t:
                text_blocks.append(f"[PAGE {p}]\n{t[:6000]}")
        user = "\n\n".join(text_blocks)
        try:
            result = llm.complete_json(FACT_SYSTEM, user)
        except (LLMError, Exception) as e:
            from .store import add_failure

            add_failure(conn, parsed.doc_id, "llm", f"Extraction call failed: {e}")
            continue
        for fact in result.get("facts", []):
            fact.setdefault("page", group[0])
            rec = _verify_store(fact, parsed.pages, parsed.doc_id, "llm", conn)
            if rec:
                facts.append(rec)
    return facts


def extract_document(parsed: ParsedDoc, llm: LLM, conn):
    """Entry point: LLM if available, heuristic otherwise. Always grounded."""
    if llm.available:
        facts = extract_llm(parsed, llm, conn)
        if facts:
            return facts, "llm"
    facts = extract_heuristic(parsed, conn)
    return facts, "heuristic"
