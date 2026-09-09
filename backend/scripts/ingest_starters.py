"""Ingest the starter PDFs through the normal pipeline (same code path as upload).

Run: uv run python scripts/ingest_starters.py [dataset]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.compare import compare_facts  # noqa: E402
from app.extract import extract_document  # noqa: E402
from app.ingest import parse_pdf  # noqa: E402
from app.llm import LLM  # noqa: E402
from app.seed_loader import seed_if_empty  # noqa: E402
from app.store import (  # noqa: E402
    add_document,
    all_fact_rows,
    connect,
    list_documents,
)

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "starter-datasets" / "starter-datasets"


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    conn = connect()
    llm = LLM()
    print(f"LLM provider: {llm.provider}")
    seed_if_empty(conn)

    folders = []
    if which in ("all", "delhivery"):
        folders.append(DATASETS / "delhivery")
    if which in ("all", "macro"):
        folders.append(DATASETS / "india-macroeconomy")

    for folder in folders:
        for pdf in sorted(folder.glob("*.pdf")):
            existing = {d["name"] for d in list_documents(conn)}
            if pdf.name in existing:
                print(f"skip (already ingested): {pdf.name}")
                continue
            print(f"\n=== {pdf.name} ===")
            doc_id = pdf.stem.lower()
            parsed = parse_pdf(pdf, doc_id, pdf.name)
            add_document(conn, doc_id, pdf.name, parsed.num_pages, parsed.chunks)
            facts, mode = extract_document(parsed, llm, conn)
            print(f"  {parsed.num_pages} pages, {len(parsed.chunks)} chunks, "
                  f"{len(facts)} facts via {mode}")
            other = [dict(f) for f in all_fact_rows(conn) if f["doc_id"] != doc_id]
            pool = other + facts
            rels = compare_facts(pool, llm, conn) if len(pool) > 1 else []
            new = [r for r in rels if doc_id in (r["fact_id_a"], r["fact_id_b"])]
            print(f"  {len(new)} new relationships")

    total_facts = conn.execute("SELECT COUNT(*) c FROM facts").fetchone()["c"]
    total_rels = conn.execute("SELECT COUNT(*) c FROM relationships").fetchone()["c"]
    print(f"\nTotals: {total_facts} facts, {total_rels} relationships")


if __name__ == "__main__":
    main()
