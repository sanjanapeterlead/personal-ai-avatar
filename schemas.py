"""
schemas.py — Pydantic request / response models for all endpoints.
"""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    answered: bool      # False → frontend shows escalation card
    provider: str       # which LLM answered ("ollama" or "gemini")
    sources: list[str] = []


class UnansweredEmailRequest(BaseModel):
    recruiter_name: str = ""
    recruiter_email: str = ""
    recruiter_company: str = ""
    questions: list[str]    # all unanswered questions from this session
