"""FastAPI application for the Fact Knowledge Layer."""
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .compare import compare_facts
from .config import CORS_ORIGINS, UPLOADS_DIR
from .extract import extract_document
from .ingest import parse_pdf
from .llm import LLM
from .seed_loader import seed_if_empty
from .store import (
    add_document,
    all_fact_rows,
    connect,
    delete_document,
    list_documents,
    list_facts,
    list_relationships,
)

STATE = {"llm": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect()
    try:
        STATE["seed"] = seed_if_empty(conn)
    finally:
        conn.close()
    STATE["llm"] = LLM()
    # Pre-warm the embedding model so the first upload is not slow.
    try:
        from .compare import load_model

        load_model()
    except Exception:  # pragma: no cover - optional dependency path
        pass
    yield


app = FastAPI(title="Fact Knowledge Layer", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "llm_provider": STATE["llm"].provider if STATE.get("llm") else "none",
        "seed": STATE.get("seed"),
    }


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Ingest a PDF: parse -> extract (LLM or heuristic) -> compare incrementally."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    doc_id = Path(file.filename).stem.lower().replace(" ", "-")[:80] + "-" + uuid.uuid4().hex[:6]
    pdf_path = UPLOADS_DIR / f"{doc_id}.pdf"
    pdf_path.write_bytes(data)

    conn = connect()
    try:
        parsed = parse_pdf(pdf_path, doc_id, file.filename)
        add_document(conn, doc_id, file.filename, parsed.num_pages, parsed.chunks)
        facts, mode = extract_document(parsed, STATE["llm"], conn)

        # Incremental: new doc's facts vs ALL existing facts (incl. seed).
        other_facts = [f for f in all_fact_rows(conn) if f["doc_id"] != doc_id]
        pool = [dict(f) for f in other_facts] + facts
        rels = compare_facts(pool, STATE["llm"], conn) if len(pool) > 1 else []
        fact_docs = {f["fact_id"]: f["doc_id"] for f in pool}
        new_rels = [
            r
            for r in rels
            if doc_id
            in (fact_docs.get(r["fact_id_a"]), fact_docs.get(r["fact_id_b"]))
        ]
        return {
            "doc_id": doc_id,
            "name": file.filename,
            "num_pages": parsed.num_pages,
            "chunks": len(parsed.chunks),
            "facts_extracted": len(facts),
            "extraction_mode": mode,
            "relationships_found": len(new_rels),
        }
    finally:
        conn.close()


@app.get("/api/documents")
def documents():
    conn = connect()
    try:
        return list_documents(conn)
    finally:
        conn.close()


@app.delete("/api/documents/{doc_id}")
def remove_document(doc_id: str):
    conn = connect()
    try:
        delete_document(conn, doc_id)
        return {"deleted": doc_id}
    finally:
        conn.close()


@app.get("/api/facts")
def facts(doc_id: str | None = None):
    conn = connect()
    try:
        return list_facts(conn, doc_id)
    finally:
        conn.close()


@app.get("/api/relationships")
def relationships(kind: str | None = None):
    conn = connect()
    try:
        return list_relationships(conn, kind)
    finally:
        conn.close()


@app.get("/api/showcase")
def showcase():
    """The four required demonstration cases, resolved against the live DB."""
    conn = connect()
    try:
        seed_path = Path(__file__).resolve().parents[1] / "seed" / "seed_knowledge.json"
        if not seed_path.exists():
            return {"cases": []}
        import json

        seed = json.loads(seed_path.read_text(encoding="utf-8"))
        cases = []
        for s in seed.get("showcase", []):
            fa = conn.execute(
                "SELECT * FROM facts WHERE fact_id = ?", (s["fact_id_a"],)
            ).fetchone()
            fb = conn.execute(
                "SELECT * FROM facts WHERE fact_id = ?", (s["fact_id_b"],)
            ).fetchone()
            if not fa or not fb:
                continue
            # If both a curated (seed) and a heuristic relationship exist for
            # this pair, prefer the curated one - it carries richer reasoning.
            rel = conn.execute(
                """SELECT * FROM relationships
                   WHERE (fact_id_a=? AND fact_id_b=?) OR (fact_id_a=? AND fact_id_b=?)
                   ORDER BY CASE WHEN source='seed' THEN 0 ELSE 1 END, created_at
                   LIMIT 1""",
                (s["fact_id_a"], s["fact_id_b"], s["fact_id_b"], s["fact_id_a"]),
            ).fetchone()
            cases.append(
                {
                    "case": s["case"],
                    "title": s["title"],
                    "narrative": s["narrative"],
                    "fact_a": dict(fa),
                    "fact_b": dict(fb),
                    "relationship": dict(rel) if rel else None,
                }
            )
        failures = conn.execute(
            "SELECT * FROM failures ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        return {"cases": cases, "failures": [dict(f) for f in failures]}
    finally:
        conn.close()
