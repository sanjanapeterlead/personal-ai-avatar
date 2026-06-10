"""
app.py — Personal AI Avatar: FastAPI entry point.

Wires together config, the vector index, and all route handlers.
Run with:
    uvicorn app:app --reload --port 8080

Provider selection (set in .env):
    LLM_PROVIDER=ollama   → local Ollama (default, needs `ollama serve`)
    LLM_PROVIDER=gemini   → Gemini free tier (needs GEMINI_API_KEY)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import LLM_PROVIDER, OLLAMA_BASE_URL, OLLAMA_MODEL, OWNER_NAME, TOP_K
from indexer import build_index
from routers import chat, health, misc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — building index…")
    index = build_index()
    app.state.retriever = index.as_retriever(similarity_top_k=TOP_K)
    if LLM_PROVIDER == "ollama":
        logger.info("Ready. Provider: ollama / %s @ %s", OLLAMA_MODEL, OLLAMA_BASE_URL)
    else:
        logger.info("Ready. Provider: %s", LLM_PROVIDER)
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=f"{OWNER_NAME}'s AI Avatar",
    description="Answers recruiter questions using personal documents.",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(misc.router)
