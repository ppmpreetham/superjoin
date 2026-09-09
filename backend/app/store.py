"""SQLite storage: documents, chunks, facts, evidence, relationships."""
import json
import sqlite3
from datetime import datetime, timezone

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    num_pages INTEGER,
    uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id),
    page INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id),
    claim TEXT NOT NULL,
    value TEXT,
    unit TEXT,
    type TEXT,
    page INTEGER,
    quote TEXT NOT NULL,
    confidence REAL,
    source TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relationships (
    rel_id TEXT PRIMARY KEY,
    fact_id_a TEXT NOT NULL REFERENCES facts(fact_id),
    fact_id_b TEXT NOT NULL REFERENCES facts(fact_id),
    kind TEXT NOT NULL,
    explanation TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(fact_id_a, fact_id_b)
);
CREATE TABLE IF NOT EXISTS failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT,
    stage TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_document(conn, doc_id, name, num_pages, chunks):
    conn.execute(
        "INSERT OR REPLACE INTO documents VALUES (?,?,?,?)",
        (doc_id, name, num_pages, now()),
    )
    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    conn.executemany(
        "INSERT INTO chunks (doc_id, page, text) VALUES (?,?,?)",
        [(doc_id, c.page, c.text) for c in chunks],
    )
    conn.commit()


def upsert_fact(conn, fact: dict) -> str:
    conn.execute(
        """INSERT OR REPLACE INTO facts
           (fact_id, doc_id, claim, value, unit, type, page, quote, confidence, source, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            fact["fact_id"],
            fact["doc_id"],
            fact["claim"],
            fact.get("value"),
            fact.get("unit"),
            fact.get("type"),
            fact.get("page"),
            fact["quote"],
            fact.get("confidence"),
            fact.get("source"),
            fact.get("created_at", now()),
        ),
    )
    conn.commit()
    return fact["fact_id"]


def upsert_relationship(conn, rel: dict) -> str:
    conn.execute(
        """INSERT OR REPLACE INTO relationships
           (rel_id, fact_id_a, fact_id_b, kind, explanation, source, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            rel["rel_id"],
            rel["fact_id_a"],
            rel["fact_id_b"],
            rel["kind"],
            rel["explanation"],
            rel.get("source"),
            rel.get("created_at", now()),
        ),
    )
    conn.commit()
    return rel["rel_id"]


def add_failure(conn, doc_id, stage, detail):
    conn.execute(
        "INSERT INTO failures (doc_id, stage, detail, created_at) VALUES (?,?,?,?)",
        (doc_id, stage, detail, now()),
    )
    conn.commit()


def list_documents(conn):
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY uploaded_at DESC"
    ).fetchall()
    out = []
    for r in rows:
        fact_count = conn.execute(
            "SELECT COUNT(*) c FROM facts WHERE doc_id = ?", (r["doc_id"],)
        ).fetchone()["c"]
        out.append({**dict(r), "fact_count": fact_count})
    return out


def list_facts(conn, doc_id=None):
    if doc_id:
        rows = conn.execute(
            "SELECT * FROM facts WHERE doc_id = ? ORDER BY created_at, fact_id", (doc_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM facts ORDER BY created_at, fact_id").fetchall()
    return [dict(r) for r in rows]


def get_fact(conn, fact_id):
    r = conn.execute("SELECT * FROM facts WHERE fact_id = ?", (fact_id,)).fetchone()
    return dict(r) if r else None


def list_relationships(conn, kind=None):
    if kind:
        rows = conn.execute(
            "SELECT * FROM relationships WHERE kind = ? ORDER BY created_at", (kind,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM relationships ORDER BY created_at").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        a = get_fact(conn, d["fact_id_a"])
        b = get_fact(conn, d["fact_id_b"])
        d["fact_a"] = a
        d["fact_b"] = b
        out.append(d)
    return out


def all_fact_rows(conn):
    return conn.execute("SELECT * FROM facts").fetchall()


def delete_document(conn, doc_id):
    """Remove a document and its facts/relationships (used on re-upload)."""
    conn.execute(
        "DELETE FROM relationships WHERE fact_id_a IN (SELECT fact_id FROM facts WHERE doc_id=?)"
        " OR fact_id_b IN (SELECT fact_id FROM facts WHERE doc_id=?)",
        (doc_id, doc_id),
    )
    conn.execute("DELETE FROM facts WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
    conn.commit()
