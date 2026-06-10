"""
routers/chat.py — POST /chat

Retrieves relevant document chunks, builds a prompt, calls the LLM,
and returns an answer with an `answered` flag the frontend uses to
decide whether to show the escalation card.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from config import LLM_PROVIDER, UNANSWERED_SIGNAL
from llm import call_llm
from prompts import build_prompt
from schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    retriever = getattr(request.app.state, "retriever", None)
    if retriever is None:
        raise HTTPException(status_code=503, detail="Still initialising. Try again shortly.")

    try:
        nodes = await asyncio.to_thread(retriever.retrieve, question)
    except Exception as exc:
        logger.exception("Retrieval failed")
        raise HTTPException(status_code=500, detail=f"Retrieval error: {exc}")

    if not nodes:
        logger.info("Q: %s | no chunks retrieved — escalating", question[:80])
        return ChatResponse(
            answer=f"{UNANSWERED_SIGNAL} in my documents about that.",
            answered=False,
            provider=LLM_PROVIDER,
            sources=[],
        )

    context_chunks  = [n.get_content() for n in nodes]
    source_previews = [c[:120].replace("\n", " ") + "…" for c in context_chunks]
    prompt          = build_prompt(question, context_chunks)
    answer          = await call_llm(prompt)

    answered = not answer.startswith(UNANSWERED_SIGNAL)
    logger.info("Q: %s | answered: %s | provider: %s", question[:80], answered, LLM_PROVIDER)
    return ChatResponse(
        answer=answer,
        answered=answered,
        provider=LLM_PROVIDER,
        sources=source_previews,
    )
