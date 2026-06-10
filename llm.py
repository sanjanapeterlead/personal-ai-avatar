"""
llm.py — LLM provider abstraction.

call_llm() is the single entry point used by all endpoint code.
It delegates to call_ollama() or call_gemini() based on LLM_PROVIDER.
"""

import asyncio
import logging
import time

import httpx
from fastapi import HTTPException

from config import (
    GEMINI_API_KEY,
    GEMINI_API_URL,
    GEMINI_MODEL,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)

logger = logging.getLogger(__name__)

# Enforce minimum gap between Gemini calls so we stay under the free-tier RPM cap.
# gemini-2.0-flash-lite free tier: ~30 RPM → 1 request per 2s is safe.
_last_gemini_call: float = 0.0
_GEMINI_MIN_INTERVAL: float = 4.0  # seconds between calls (conservative)


async def call_ollama(prompt: str) -> str:
    """Send a prompt to the local Ollama instance and return the response text."""
    payload = {
        "model":   OLLAMA_MODEL,
        "prompt":  prompt,
        "stream":  False,
        "options": {"temperature": 0.25, "num_predict": 600},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            r = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
            r.raise_for_status()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
                    "Run `ollama serve` first."
                ),
            )
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Ollama error: {exc.response.text}",
            )
    return r.json().get("response", "").strip()


async def call_gemini(prompt: str) -> str:
    """Send a prompt to the Gemini API and return the response text.

    Throttles outgoing calls to _GEMINI_MIN_INTERVAL seconds apart so the
    free-tier RPM cap is never reached. Does NOT retry on 429 — retrying a
    rate-limited request just wastes more quota.
    """
    global _last_gemini_call
    elapsed = time.monotonic() - _last_gemini_call
    if elapsed < _GEMINI_MIN_INTERVAL:
        wait = _GEMINI_MIN_INTERVAL - elapsed
        logger.debug("Throttling Gemini call by %.1fs", wait)
        await asyncio.sleep(wait)
    _last_gemini_call = time.monotonic()

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.25, "maxOutputTokens": 600},
    }
    url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            r = await client.post(url, json=payload)
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise HTTPException(
                    status_code=429,
                    detail="Gemini rate limit reached. Please wait a few seconds and try again.",
                )
            raise HTTPException(
                status_code=502,
                detail=f"Gemini error: {exc.response.text}",
            )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail="Cannot reach Gemini API.",
            )

    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        logger.error("Unexpected Gemini response shape: %s", data)
        raise HTTPException(
            status_code=502,
            detail="Unexpected response shape from Gemini.",
        ) from exc


async def call_llm(prompt: str) -> str:
    """Single entry point for all LLM calls. Routes to the configured provider."""
    if LLM_PROVIDER == "gemini":
        return await call_gemini(prompt)
    return await call_ollama(prompt)
