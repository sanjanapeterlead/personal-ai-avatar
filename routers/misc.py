"""
routers/misc.py — GET /config, POST /mailto-body, GET /

/config   — returns public owner info to the frontend (no secrets)
/mailto-body — generates a pre-filled mailto: URL (client-side email flow)
/         — serves index.html
"""

import urllib.parse
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from config import LLM_PROVIDER, OWNER_EMAIL, OWNER_NAME, OWNER_WHATSAPP
from schemas import UnansweredEmailRequest

router = APIRouter()


@router.get("/config")
def config():
    """Public owner config for the frontend. Never exposes secrets."""
    return {
        "owner_name":      OWNER_NAME,
        "owner_email":     OWNER_EMAIL,
        "has_whatsapp":    bool(OWNER_WHATSAPP),
        "whatsapp_number": OWNER_WHATSAPP,
        "llm_provider":    LLM_PROVIDER,
    }


@router.post("/mailto-body")
def mailto_body(payload: UnansweredEmailRequest):
    """
    Generates a pre-filled mailto: URL the frontend opens to let the recruiter
    send an email. Nothing is sent server-side — the recruiter's own email
    client handles delivery.
    """
    q_list  = "\n".join(f"  • {q}" for q in payload.questions)
    subject = f"Questions for {OWNER_NAME} — via AI Avatar"
    body = (
        f"Hi {OWNER_NAME},\n\n"
        "I was chatting with your AI avatar and had a few questions it couldn't answer:\n\n"
        f"{q_list}\n\n"
        "Could you get back to me when you have a moment?\n\n"
        f"Best,\n{payload.recruiter_name or 'A recruiter'}"
        + (f"\n{payload.recruiter_company}" if payload.recruiter_company else "")
        + (f"\n{payload.recruiter_email}"   if payload.recruiter_email   else "")
    )
    mailto_url = (
        f"mailto:{OWNER_EMAIL}"
        f"?subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(body)}"
        + (
            f"&cc={urllib.parse.quote(payload.recruiter_email)}"
            if payload.recruiter_email else ""
        )
    )
    return {"mailto_url": mailto_url, "subject": subject}


@router.get("/")
def serve_widget():
    if Path("index.html").exists():
        return FileResponse("index.html")
    return {"message": "index.html not found in project root."}
