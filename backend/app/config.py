import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "knowledge.db"
UPLOADS_DIR = DATA_DIR / "uploads"
SEED_PATH = ROOT / "seed" / "seed_knowledge.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# --- LLM provider (optional; system falls back to heuristics without a key) ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").lower()  # anthropic | openai | ""
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))


def active_provider() -> str:
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return "anthropic"
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return "openai"
    if not LLM_PROVIDER:
        if ANTHROPIC_API_KEY:
            return "anthropic"
        if OPENAI_API_KEY:
            return "openai"
    return "none"


EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
EMBED_CANDIDATES = int(os.getenv("EMBED_CANDIDATES", "3"))
EMBED_THRESHOLD = float(os.getenv("EMBED_THRESHOLD", "0.45"))

CHUNK_CHARS = int(os.getenv("CHUNK_CHARS", "3000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
PAGES_PER_LLM_CALL = int(os.getenv("PAGES_PER_LLM_CALL", "3"))

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
).split(",")
