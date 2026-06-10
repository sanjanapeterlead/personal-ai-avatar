"""
routers/health.py — GET /health

Reports whether the LLM provider and the vector index are ready.
"""

import httpx
from fastapi import APIRouter, Request

from config import GEMINI_API_KEY, GEMINI_MODEL, LLM_PROVIDER, OLLAMA_BASE_URL

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    provider_ok = False
    detail: dict = {}

    if LLM_PROVIDER == "ollama":
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                provider_ok = r.status_code == 200
                if provider_ok:
                    detail = {
                        "available_models": [
                            m["name"] for m in r.json().get("models", [])
                        ]
                    }
        except Exception:
            pass
    else:  # gemini
        provider_ok = bool(GEMINI_API_KEY)
        detail = {"model": GEMINI_MODEL}

    return {
        "status":         "ok",
        "provider":       LLM_PROVIDER,
        "provider_ready": provider_ok,
        "index_ready":    getattr(request.app.state, "retriever", None) is not None,
        **detail,
    }
