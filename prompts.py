"""
prompts.py — System prompt and prompt-building helpers.

UNANSWERED_SIGNAL is imported from config so the value stays in one place.
The phrase in SYSTEM_PROMPT rule #2 must match UNANSWERED_SIGNAL exactly.
"""

from config import OWNER_NAME, UNANSWERED_SIGNAL

SYSTEM_PROMPT = (
    f"You are a professional AI assistant representing {OWNER_NAME}. "
    "Your job is to help recruiters learn about her background, skills, "
    "projects, and interests.\n\n"
    "RULES:\n"
    "1. Answer using ONLY the context provided. Do not invent facts.\n"
    f'2. If the context does not contain enough information, respond with '
    f'exactly: "{UNANSWERED_SIGNAL}" — you may add one polite sentence after.\n'
    f"3. Speak in third person — refer to {OWNER_NAME} by name or as 'she/her'.\n"
    "4. Be warm, professional, and concise.\n"
    f"5. For salary, availability, or sensitive questions, say {OWNER_NAME} "
    "would prefer to discuss those directly."
)


def build_prompt(question: str, context_chunks: list[str]) -> str:
    """Assemble the full LLM prompt from system instructions and retrieved context."""
    context_block = "\n\n---\n\n".join(context_chunks)
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"CONTEXT:\n\n{context_block}\n\n"
        f"RECRUITER QUESTION: {question}\n\n"
        f"ANSWER:"
    )
