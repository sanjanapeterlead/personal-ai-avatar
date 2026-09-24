"""
slack.py — Slack escalation notifier.

Posts unanswered questions to a Slack channel via an Incoming Webhook, in
real time, so the owner finds out without the recruiter having to do
anything extra. This runs as a FastAPI background task after the /chat
response is already sent — it must never raise, since there is no caller
left to handle an exception.
"""

import logging
from datetime import datetime, timezone

import httpx

from config import OWNER_NAME, SLACK_WEBHOOK_URL

logger = logging.getLogger(__name__)


async def notify_slack_unanswered(question: str, session_id: str) -> None:
    """Best-effort Slack notification for a question the avatar couldn't answer.

    Silently does nothing if SLACK_WEBHOOK_URL is not configured. Any network
    or Slack-side error is logged and swallowed — this must never bubble up.
    """
    if not SLACK_WEBHOOK_URL:
        logger.debug("SLACK_WEBHOOK_URL not set — skipping Slack notification.")
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    short_session = (session_id or "unknown")[:8]

    payload = {
        "text": f"Unanswered question for {OWNER_NAME}'s AI avatar: {question}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":rotating_light: *{OWNER_NAME}'s AI avatar couldn't answer a "
                        "recruiter's question*"
                    ),
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f">{question}"},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Session `{short_session}` · {timestamp}",
                    }
                ],
            },
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(SLACK_WEBHOOK_URL, json=payload)
            r.raise_for_status()
    except Exception:
        logger.exception("Slack notification failed for session %s", short_session)
