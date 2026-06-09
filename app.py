"""
app.py — Personal AI Avatar Backend
FastAPI server that answers recruiter questions about Sanjana using:
- Multiple document types: resume PDF, bio, project writeups, blog posts, GitHub READMEs
- HuggingFace sentence-transformers for local embeddings + vector retrieval
- Ollama as the local LLM (free, runs on your machine)
- LlamaIndex for document indexing and retrieval

Folder structure expected:
    data/
      resume/        ← resume PDF(s)
      bio/           ← personal bio, about-me text/markdown files
      projects/      ← project writeups, case studies (PDF, MD, TXT)
      blog/          ← blog posts or articles (MD, TXT)
      github/        ← copied GitHub README.md files

Usage:
    1. ollama serve
    2. ollama pull llama3.2
    3. uvicorn app:app --reload --port 8000
"""

import os
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    Settings,
    StorageContext,
    load_index_from_storage,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.core.node_parser import SentenceSplitter

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "llama3.2")

# Your contact details — set via environment variables or edit directly
OWNER_NAME      = os.environ.get("AVATAR_OWNER_NAME", "Sanjana")
OWNER_EMAIL     = os.environ.get("AVATAR_OWNER_EMAIL", "your@email.com")
# WhatsApp: just your number with country code, no spaces/dashes e.g. "12125551234"
OWNER_WHATSAPP  = os.environ.get("AVATAR_OWNER_WHATSAPP", "")   # leave blank to hide button

DATA_DIR        = Path("data")
PERSIST_DIR     = Path(".index_cache")

EMBED_MODEL     = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K           = 6   # slightly higher than resume-only — more doc types = more noise

# Sub-folders inside data/ that will be indexed.
# Add/remove folders to match what you actually have.
DATA_SUBDIRS = ["resume", "bio", "projects", "blog", "github"]

# Supported file extensions LlamaIndex will read from each folder
SUPPORTED_EXTS = [".pdf", ".md", ".txt", ".docx", ".json"]

# ─────────────────────────────────────────────────────────────────────────────
# Index builder
# ─────────────────────────────────────────────────────────────────────────────
def collect_documents():
    """
    Walk DATA_DIR (and optional sub-folders) and load all supported files.
    Falls back gracefully if a sub-folder doesn't exist yet.
    """
    all_docs = []

    # First try organised sub-folders
    subdirs_found = []
    for sub in DATA_SUBDIRS:
        p = DATA_DIR / sub
        if p.exists() and any(p.glob("**/*")):
            subdirs_found.append(str(p))

    if subdirs_found:
        for d in subdirs_found:
            docs = SimpleDirectoryReader(
                d,
                recursive=True,
                required_exts=SUPPORTED_EXTS,
            ).load_data()
            logger.info("  %s → %d document(s)", d, len(docs))
            all_docs.extend(docs)
    else:
        # Flat data/ folder (original layout) — backwards compatible
        logger.info("No sub-folders found, reading data/ directly")
        all_docs = SimpleDirectoryReader(
            str(DATA_DIR),
            recursive=True,
            required_exts=SUPPORTED_EXTS,
        ).load_data()

    return all_docs


def build_index() -> VectorStoreIndex:
    embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)
    llm = Ollama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, request_timeout=120.0)
    Settings.embed_model = embed_model
    Settings.llm = llm

    if PERSIST_DIR.exists():
        logger.info("Loading index from cache at %s", PERSIST_DIR)
        storage_context = StorageContext.from_defaults(persist_dir=str(PERSIST_DIR))
        return load_index_from_storage(storage_context)

    logger.info("Building index from %s …", DATA_DIR)
    if not DATA_DIR.exists():
        raise FileNotFoundError(
            f"'{DATA_DIR}' folder not found. "
            "Create it with sub-folders: resume/, bio/, projects/, blog/, github/"
        )

    documents = collect_documents()
    if not documents:
        raise FileNotFoundError(
            f"No supported files ({SUPPORTED_EXTS}) found under {DATA_DIR}/. "
            "Add your documents and restart."
        )
    logger.info("Total documents loaded: %d", len(documents))

    # Slightly larger chunks than resume-only — project writeups and blog posts
    # have longer coherent passages worth keeping together.
    splitter = SentenceSplitter(chunk_size=600, chunk_overlap=80)
    nodes = splitter.get_nodes_from_documents(documents)
    logger.info("Split into %d chunks", len(nodes))

    index = VectorStoreIndex(nodes)
    index.storage_context.persist(persist_dir=str(PERSIST_DIR))
    logger.info("Index persisted to %s", PERSIST_DIR)
    return index


# ─────────────────────────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────────────────────────
_query_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _query_engine
    logger.info("Starting up — building index…")
    index = build_index()
    _query_engine = index.as_query_engine(similarity_top_k=TOP_K)
    logger.info("Ready. Model: %s @ %s", OLLAMA_MODEL, OLLAMA_BASE_URL)
    yield
    logger.info("Shutting down.")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=f"{OWNER_NAME}'s AI Avatar",
    description="Answers recruiter questions using personal documents.",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str
    answered: bool          # False = avatar couldn't find info → trigger escalation UI
    sources: list[str] = []

class UnansweredEmailRequest(BaseModel):
    recruiter_name: str = ""
    recruiter_email: str = ""
    recruiter_company: str = ""
    questions: list[str]    # all questions the avatar couldn't answer this session


# LlamaIndex returns this string when no relevant context is found
UNANSWERED_SIGNAL = "Empty Response"


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        pass
    return {
        "status": "ok",
        "model": OLLAMA_MODEL,
        "ollama_reachable": ollama_ok,
        "index_ready": _query_engine is not None,
    }


@app.get("/config")
def config():
    """
    Returns public contact config to the frontend.
    Never exposes secrets — only what's needed to build mailto/WhatsApp links.
    """
    return {
        "owner_name":   OWNER_NAME,
        "owner_email":  OWNER_EMAIL,
        "has_whatsapp": bool(OWNER_WHATSAPP),
        "whatsapp_number": OWNER_WHATSAPP,  # frontend builds the wa.me link
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    if _query_engine is None:
        raise HTTPException(status_code=503, detail="Still initialising. Try again shortly.")

    try:
        # query_engine.query() is synchronous — run it off the event loop thread
        response = await asyncio.to_thread(_query_engine.query, question)
    except Exception as exc:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=f"Query error: {exc}")

    answer = str(response.response or "").strip()

    # LlamaIndex returns "Empty Response" when no relevant chunks were found
    if not answer or answer == UNANSWERED_SIGNAL:
        logger.info("Q: %s | no relevant context — escalating", question[:80])
        return ChatResponse(
            answer="I don't have that information in my documents about that.",
            answered=False,
            sources=[],
        )

    sources = [
        n.get_content()[:120].replace("\n", " ") + "…"
        for n in (response.source_nodes or [])
    ]
    logger.info("Q: %s | answered: True", question[:80])
    return ChatResponse(answer=answer, answered=True, sources=sources)


@app.post("/mailto-body")
def mailto_body(payload: UnansweredEmailRequest):
    """
    Generates a pre-filled mailto: URL the frontend opens to let
    the recruiter send an email. Nothing is sent server-side —
    the recruiter's own email client handles delivery.

    To upgrade to server-side sending later (EmailJS / SMTP),
    replace this endpoint's body only — the frontend call stays identical.
    """
    q_list = "\n".join(f"  • {q}" for q in payload.questions)

    subject = f"Questions for {OWNER_NAME} — via AI Avatar"

    body = (
        f"Hi {OWNER_NAME},\n\n"
        f"I was chatting with your AI avatar and had a few questions it couldn't answer:\n\n"
        f"{q_list}\n\n"
        f"Could you get back to me when you have a moment?\n\n"
        f"Best,\n"
        f"{payload.recruiter_name or 'A recruiter'}"
        + (f"\n{payload.recruiter_company}" if payload.recruiter_company else "")
        + (f"\n{payload.recruiter_email}" if payload.recruiter_email else "")
    )

    import urllib.parse
    mailto_url = (
        f"mailto:{OWNER_EMAIL}"
        f"?subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(body)}"
        + (f"&cc={urllib.parse.quote(payload.recruiter_email)}" if payload.recruiter_email else "")
    )

    return {"mailto_url": mailto_url, "subject": subject}


@app.get("/")
def serve_widget():
    if Path("index.html").exists():
        return FileResponse("index.html")
    return {"message": "index.html not found in project root."}