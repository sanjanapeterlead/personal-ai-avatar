"""
config.py — All environment variables, path constants, and startup validation.

Every value the app needs from the environment is read here once.
Import from this module everywhere else — never call os.environ directly.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── LLM provider ──────────────────────────────────────────────────────────────
# Set LLM_PROVIDER=ollama  (default, runs locally — needs `ollama serve`)
# Set LLM_PROVIDER=gemini  (free cloud tier, needs GEMINI_API_KEY)
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "llama3.2")

# ── Gemini free tier ──────────────────────────────────────────────────────────
# gemini-1.5-flash: 15 RPM, 1 M tokens/day, no credit card required
# Get key: https://aistudio.google.com/app/apikey
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-lite")
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    f"/{GEMINI_MODEL}:generateContent"
)

# ── Owner contact (set in .env — never hard-code) ─────────────────────────────
OWNER_NAME     = os.environ.get("AVATAR_OWNER_NAME", "Sanjana")
OWNER_EMAIL    = os.environ.get("AVATAR_OWNER_EMAIL", "your@email.com")
OWNER_WHATSAPP = os.environ.get("AVATAR_OWNER_WHATSAPP", "")  # leave blank to hide button

# ── Storage paths ─────────────────────────────────────────────────────────────
DATA_DIR    = Path("data")
PERSIST_DIR = Path(".index_cache")

# ── RAG tuning (do not change without deleting .index_cache/ and rebuilding) ──
EMBED_MODEL    = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K          = 6
DATA_SUBDIRS   = ["resume", "bio", "projects", "blog", "github"]
SUPPORTED_EXTS = [".pdf", ".md", ".txt", ".docx", ".json"]

# ── Unanswered-question signal phrase ─────────────────────────────────────────
# Must match the phrase in SYSTEM_PROMPT (prompts.py) exactly.
# The /chat endpoint checks answer.startswith(UNANSWERED_SIGNAL).
UNANSWERED_SIGNAL = "I don't have that information"

# ── Startup validation ────────────────────────────────────────────────────────
if LLM_PROVIDER not in ("ollama", "gemini"):
    raise EnvironmentError(
        f"Unknown LLM_PROVIDER='{LLM_PROVIDER}'. Must be 'ollama' or 'gemini'."
    )
if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise EnvironmentError(
        "LLM_PROVIDER=gemini requires GEMINI_API_KEY.\n"
        "Get a free key at: https://aistudio.google.com/app/apikey"
    )
