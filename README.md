# Fact Knowledge Layer

Upload PDFs → extract grounded facts → compare across documents → see what corroborates, contradicts, or reconciles with context.

**Stack:** Python (FastAPI + PyMuPDF + SQLite + sentence-transformers) · React (Vite) · LLM-optional.

---

## Setup and Run

**Prereqs:** Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 18+.

### 1. Backend (port 8000)

```bash
cd backend
uv sync                      # install deps into .venv
uv run uvicorn app.main:app --port 8000
```

First start seeds the knowledge base (40 facts verified page-by-page against the starter PDFs, 14 curated cross-document relationships), pre-loads the local embedding model (~90 MB download on first ever run), then serves:

- `POST /api/upload` — multipart PDF; returns extraction + relationship stats
- `GET /api/documents` · `GET /api/facts?doc_id=` · `GET /api/relationships?kind=corroborates|contradicts|reconciles`
- `GET /api/showcase` — the four required cases resolved against the live DB
- `DELETE /api/documents/{id}`

Swagger UI: `http://localhost:8000/docs`

### 2. Frontend (port 5173)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Tabs: Showcase (the four cases), Facts, Relationships, **Graph** (force-directed fact-relationship graph — click a node for its claim, quote and page), Documents. UI is styled in the [Nothing design language](https://github.com/dominikmartn/nothing-design-skill) (OLED black, Space Grotesk / Space Mono / Doto, monochrome + status colors). CORS is configured for `localhost:5173` / `127.0.0.1:5173` (override with `CORS_ORIGINS` env var).

### Optional: enable a real LLM

```bash
export ANTHROPIC_API_KEY=sk-...        # or OPENAI_API_KEY=sk-...
export LLM_PROVIDER=anthropic          # anthropic | openai
```

With a key, uploads are extracted by the LLM (grounded JSON: claim + quote + page per fact) and relationships are classified by a second LLM pass that cites evidence. Without a key, everything still works via the seed knowledge + deterministic heuristic pipeline (and says so — the UI shows the active mode).

### Demo video

> 📹 *(add link here — ≤3 min: upload a PDF → facts appear → the four showcase cases)*

---

## Approach

```
                ┌──────────────────────────────────────────────────┐
                │                    React UI                      │
                │   upload · facts · relationships · 4 cases       │
                └──────────────────────┬───────────────────────────┘
                                       │ JSON (CORS: 5173→8000)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ FastAPI                                                                     │
│                                                                             │
│  1. INGEST      PyMuPDF → per-page text → page-aware chunks (merge sparse,  │
│                 split dense pages w/ overlap). doc_id, page on every chunk. │
│                                                                             │
│  2. EXTRACT     LLM path: per-page-group prompts force JSON with a verbatim │
│                 quote + page per fact.                                      │
│                 No-LLM path: number-bearing sentences become verbatim facts.│
│                 GROUNDING GATE: every fact's quote is located in the actual │
│                 page text (normalized whitespace/punctuation; fuzzy fallback│
│                 w/ trigram similarity). Ungrounded facts are REJECTED and   │
│                 logged to the failures table.                              │
│                                                                             │
│  3. COMPARE     sentence-transformers embeddings → candidate pairs across   │
│                 docs → LLM classifier (corroborates/contradicts/reconciles/ │
│                 unrelated, citing quotes) or numeric heuristic (≤1% = cor-  │
│                 roborates, ≤15% = reconciles, >3x scale = "units mismatch,  │
│                 needs review", else contradicts).                          │
│                                                                             │
│  4. STORE       SQLite: documents, chunks, facts, relationships, failures.  │
│                 rel_id is deterministic per fact-pair → idempotent re-runs. │
└─────────────────────────────────────────────────────────────────────────────┘
```

### How the four cases are demonstrated

1. **Corroboration** — deck "EBITDA ₹127 Cr / 1.6%" vs annual report "EBITDA ₹1,266.41 Mn": different units, different precision, same fact (₹1,266.41 Mn = ₹126.6 Cr). Also parcel volume (740 Mn both docs) and PTL tonnage (1.4 Mn tons ≈ 1,429K tonnes).
2. **Genuine contradiction** — IMF projects FY2025/26 CPI inflation at **2.8%**; RBI projects **4.0%** for the same year, same indicator. The system flags it, cites both quotes, notes the publication-order context, and refuses to pick a winner.
3. **Reconciliation via context** — prospectus (May 2022) lists Suvir Suren Sujan as a current director; the FY24 annual report says he resigned Aug 24, 2023 → **time**. Standalone loss ₹1,679.68 Mn vs consolidated ₹2,491.86 Mn → **scope**. Survey Apr–Dec CPI 4.9% vs RBI full-year 4.6% → **coverage window**. Deck ₹8,142 Cr services revenue vs AR ₹81,415.38 Mn revenue from operations → **units + rounding + label scope**.
4. **Extraction failure** — the earnings deck's segment charts extract with numbers separated from labels (PDF text-order jumbling); naive label-adjacency reads "PTL revenue ₹1,429 Cr" when 1,429 is actually **tonnage** in '000 tonnes. Detected via cross-document check against the AR's statutory ₹15,174.05 Mn (= ₹1,517.4 Cr). Documented in the failure log, surfaced in the UI, with a planned fix (bbox-aware chart extraction).

### Key decisions & trade-offs

- **Grounding gate over trust-the-LLM.** The LLM path returns JSON, but the system itself re-locates every quote in the source text. Cost: some good facts get rejected when quoting is imperfect. Benefit: no hallucinated evidence can enter the store — and this gate already caught a real transcription error during development (curly apostrophe U+2019 vs ASCII `'`).
- **LLM-optional, not LLM-dependent.** The evaluation dataset is fully reproducible without any API key (seed + heuristics); with a key the same code paths upgrade to LLM extraction/comparison. Trade-off: the heuristic mode is crude (sentence-level facts, numeric-only comparison) and the UI honestly labels which mode produced each item.
- **SQLite over a vector DB.** Facts/evidence are the core; embeddings are used transiently for candidate recall, not as the source of truth. Simpler to inspect, zero infra.
- **Deterministic relationship IDs** (`sha1(sorted(fact_a, fact_b))`) make re-ingestion idempotent and enable incremental uploads: a new PDF compares only against existing facts, and seed (human-curated) relationships are never overwritten by pipeline output.
- **Chunking by page with merge/split**: pages merge up to ~3k chars; dense pages split with 200-char overlap. Trade-off: tables that straddle chunks can lose alignment — visible in the chart-extraction failure above.
- **AI tools used:** Claude (via the Codebuff/Freebuff agent) implemented this codebase end-to-end and performed the "LLM provider" role for the seed knowledge: reading the six starter PDFs, proposing candidate facts/relationships, and writing the curated explanations. The quote-verification step then proved every seed fact against the actual PDFs (`backend/scripts/build_seed.py` prints per-fact verification).

---

## Limitations and Next Steps

Honest list of what does not work yet:

- **Chart/table extraction is the weakest link.** The PTL chart misread (case 4) is structural: `get_text("text")` linearizes PDFs and scatters chart labels/values. Next: `page.get_text("words")` bbox clustering to bind numbers to nearby titles/legends, and table-aware extraction (`page.find_tables()`).
- **Heuristic facts are noisy.** Sentence-level extraction grabs boilerplate (headers, addresses). With no LLM key, precision is low by design; the confidence field (0.3) reflects it. Next: better sentence filters, entity-anchored extraction.
- **The numeric comparator is unit-blind.** It guesses that a >3x gap is a units issue, but cannot convert crore↔million or detect "% YoY" vs "absolute". Next: a small unit-normalization layer (currency scale, percent, counts) before comparison.
- **Cross-document candidate recall uses one embedding model.** MiniLM is fast but can miss paraphrases with little lexical overlap; threshold 0.45 trades recall for noise. Next: hybrid recall (embedding + entity/value overlap).
- **No authentication, no async processing.** Upload blocks the request (~20 s heuristic, LLM longer); a job queue + polling/SSE would be the production shape.
- **Evaluation is qualitative.** No precision/recall harness over a labeled fact set. Next: small golden set + scoring script.

## Additional Notes

- `backend/seed/seed_source.json` (raw curation) → `backend/scripts/build_seed.py` (verifies quotes against PDFs, exits non-zero on any failure) → `backend/seed/seed_knowledge.json` (committed artifact loaded on first run). Regenerating is one command: `uv run python scripts/build_seed.py`.
- `backend/scripts/ingest_starters.py` runs the starter PDFs through the exact upload code path from the CLI — useful for testing without the UI.
- Starter PDFs live in `starter-datasets/` (see its READMEs for provenance and curation details).
- Everything runs locally; no paid service is required for the demo.
