"""Loads seed_knowledge.json into the database on first run.

This is how the app "ships with intelligence" without an LLM key: the seed
facts were extracted from the starter PDFs (quotes verified page-by-page at
build time by scripts/build_seed.py), and relationships were classified by a
human-in-the-loop pass. New PDFs uploaded at runtime go through the live
pipeline (LLM if configured, heuristics otherwise).
"""
import json

from .config import SEED_PATH
from .compare import candidate_pairs, heuristic_classify
from .store import (
    add_failure,
    connect,
    list_facts,
    upsert_fact,
    upsert_relationship,
)


def seed_if_empty(conn) -> dict:
    if conn.execute("SELECT COUNT(*) c FROM facts").fetchone()["c"] > 0:
        return {"seeded": False, "reason": "database already contains facts"}
    if not SEED_PATH.exists():
        return {"seeded": False, "reason": "no seed file found"}

    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))

    import hashlib
    from datetime import datetime, timezone

    for d in seed["documents"]:
        conn.execute(
            "INSERT OR IGNORE INTO documents VALUES (?,?,?,?)",
            (d["doc_id"], d["name"], None, datetime.now(timezone.utc).isoformat()),
        )
    conn.commit()

    for f in seed["facts"]:
        upsert_fact(conn, f)

    for r in seed["curated_relationships"]:
        upsert_relationship(conn, {**r, "created_at": datetime.now(timezone.utc).isoformat()})

    for fl in seed.get("failures", []):
        add_failure(conn, fl.get("doc_id"), fl["stage"], fl["detail"])

    # Also run the deterministic heuristic classifier over the curated candidate
    # pairs so the store reflects what the heuristic pipeline alone would find.
    facts = {(f["fact_id"]): f for f in list_facts(conn)}
    heur = 0
    for a_id, b_id in seed.get("candidate_pairs", []):
        fa, fb = facts.get(a_id), facts.get(b_id)
        if not fa or not fb:
            continue
        hc = heuristic_classify(fa, fb)
        if hc is None:
            continue
        kind, expl = hc
        rel_id = "r_" + hashlib.sha1("|".join(sorted([a_id, b_id])).encode()).hexdigest()[:12]
        upsert_relationship(
            conn,
            {
                "rel_id": rel_id,
                "fact_id_a": a_id,
                "fact_id_b": b_id,
                "kind": kind,
                "explanation": expl + " [heuristic classifier]",
                "source": "heuristic-seed",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        heur += 1

    return {
        "seeded": True,
        "facts": len(seed["facts"]),
        "relationships": len(seed["curated_relationships"]),
        "heuristic_relationships": heur,
    }
