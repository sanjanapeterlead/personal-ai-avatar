# CLAUDE.md — Project Rules for Claude Code Sessions

> This file tells Claude Code how to work in this repo.

---

## What this project is

A **personal AI avatar** that represents Sanjana to recruiters.
It answers questions from her documents and escalates unanswerable questions via email.

- **Backend:** FastAPI (`app.py`)
- **Embeddings:** HuggingFace `all-MiniLM-L6-v2` (local, free)
- **LLM:** Ollama via HTTP (`/api/generate`) — no API key needed
- **Frontend:** `index.html` — self-contained, embeddable widget
- **Data:** `data/` with sub-folders: `resume/`, `bio/`, `projects/`, `blog/`, `github/`

---

## Critical constraints

1. **No hard-coded credentials.** Owner name, email, and WhatsApp number are
   read from environment variables (`AVATAR_OWNER_*`). Never put them in code.

2. **Do not touch `.index_cache/`** unless the user asks to rebuild the index.
   To rebuild: delete the folder and restart. Rebuilding re-embeds all documents.

3. **Use LlamaIndex's query engine for LLM calls.** Set `Settings.llm = Ollama(...)`
   and use `index.as_query_engine(llm=llm)`. Do NOT call Ollama manually via HTTP —
   LlamaIndex's query engine has proven internal prompts that reliably return
   `"Empty Response"` on missing context, preventing hallucination.

4. **`index.html` is intentionally one file.** Keep it self-contained so it
   works as a GitHub Pages drop-in and as an `<iframe>` embed. Do not split
   it unless explicitly asked.

5. **The email flow is client-side only** (`mailto:` link). Do not add server-
   side email sending without explicit instruction — it requires SMTP credentials
   and changes the security model.

6. **`answered: bool` in ChatResponse is load-bearing.** The frontend uses it
   to decide whether to show the escalation card. Do not remove or rename it.

7. Always note-down Issues faced in a separate document called, project-issues-faced-and-solved.md, make sure to keep in detail about it so that user could go through it.

---

## Key files

| File | Purpose |
|---|---|
| `app.py` | FastAPI backend — RAG pipeline + mailto endpoint |
| `index.html` | Chat widget with escalation UX |
| `requirements.txt` | Python dependencies |
| `data/` | All source documents (sub-folders by type) |
| `.index_cache/` | Persisted vector index (auto-generated, gitignored) |
| `CLAUDE.md` | This file |
| `README.md` | Full setup and architecture docs |

---

## Data folder conventions

```
data/
  resume/    ← PDF, one per version of the resume
  bio/       ← Markdown or plain text, free-form personal narrative
  projects/  ← One file per project, MD or PDF preferred
  blog/      ← Blog posts or articles, MD or TXT
  github/    ← Copied README.md files renamed to avoid collisions
```

Files can be added to any sub-folder. Delete `.index_cache/` to force a
rebuild after changes.

---

## How to run

```bash
# 1. Start Ollama
ollama serve

# 2. Set contact details
export AVATAR_OWNER_NAME="Sanjana"
export AVATAR_OWNER_EMAIL="sanjana@email.com"
export AVATAR_OWNER_WHATSAPP="12125551234"  # optional

# 3. Start server
uvicorn app:app --reload --port 8000
```

---

## Unanswered question detection

LlamaIndex's query engine returns the string `"Empty Response"` when no
relevant context is found. `app.py` checks `answer == UNANSWERED_SIGNAL`
and sets `answered=False`. The frontend reads this flag to show the
escalation card.

**Do not change `UNANSWERED_SIGNAL`** without also updating the check in
the `/chat` endpoint.

---

## Conventions

- Python: PEP 8, type hints, docstrings on public functions, `logging` not `print`
- Errors: `HTTPException` with meaningful status codes (400/502/503)
- Frontend: no frameworks, no build step — vanilla JS only
- Secrets: environment variables only, never in source

---

## What NOT to change without discussion

- `EMBED_MODEL` — changing invalidates the persisted index
- `chunk_size=600, chunk_overlap=80` — tuned for mixed doc types
- `similarity_top_k=6` — higher than resume-only to handle multiple doc types
- `UNANSWERED_SIGNAL` constant and matching system prompt phrase
- `answered` field in `ChatResponse`