# Personal AI Avatar

An AI assistant that represents you to recruiters — answers questions about your background using your own documents, and gracefully escalates to you when it can't.

**Stack:** Ollama (local LLM, free) · HuggingFace embeddings · FastAPI · vanilla JS widget

---

## What it does

- Answers recruiter questions from your actual documents (resume, bio, projects, blog posts, GitHub READMEs)
- Detects when it can't answer and shows an escalation card with a direct email button
- Tracks all unanswered questions in a session and lets the recruiter send them all to you in one pre-filled email (opens their email client — no server-side sending, no keys needed)
- WhatsApp button ready to activate with your number
- Embeddable anywhere via `<iframe>`

---

## Architecture

```
data/
  resume/   → resume PDF(s)
  bio/       → personal bio, about-me text or markdown
  projects/  → project writeups, case studies
  blog/      → blog posts, articles
  github/    → copied GitHub README.md files
       │
       ▼
SimpleDirectoryReader + SentenceSplitter (600 tok / 80 overlap)
       │
       ▼
HuggingFace all-MiniLM-L6-v2    ← local embeddings, no API key
       │
       ▼
VectorStoreIndex (.index_cache/) ← built once, reused on restart
       │
   query time:
   question → embed → cosine similarity → top-6 chunks
       │
       ▼
Ollama llama3.2                  ← free, runs on your machine
   system prompt + context + question
       │
       ▼
FastAPI /chat  →  { answer, answered: bool }
       │
   if answered=false:
       ├── escalation card in UI
       └── /mailto-body  →  opens recruiter's email client
                             with all unanswered questions pre-filled
```

---

## Folder structure

```
personal-ai-avatar/
├── app.py              ← FastAPI backend
├── index.html          ← chat widget (self-contained)
├── requirements.txt
├── CLAUDE.md           ← rules for Claude Code sessions
├── README.md
├── data/
│   ├── resume/         ← drop your resume PDF here
│   ├── bio/            ← your_bio.md or about_me.txt
│   ├── projects/       ← project_1.md, case_study.pdf, etc.
│   ├── blog/           ← post_1.md, article.txt, etc.
│   └── github/         ← copy README.md files from your repos here
└── .index_cache/       ← auto-generated, gitignored
```

---

## Setup

Copy `.env.example` to `.env` and fill in your settings before starting.

### 1. Install Ollama

**macOS / Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```
**Windows:** [ollama.com/download](https://ollama.com/download)

### 2. Pull a model

```bash
ollama pull llama3.2        # ~2 GB — recommended
# ollama pull llama3.2:1b  # ~800 MB — use if RAM is tight
# ollama pull mistral       # ~4 GB — more capable
```

### 3. Install Python dependencies

```bash
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Add your documents

```bash
mkdir -p data/resume data/bio data/projects data/blog data/github

# Resume
cp your_resume.pdf data/resume/

# Bio — create a markdown file
cat > data/bio/about_me.md << 'BIO'
# About Me
Write 3–5 paragraphs about yourself: who you are, what drives you,
what kind of work excites you, what you're looking for next.
BIO

# Projects — one file per project works well
cat > data/projects/project_name.md << 'PROJ'
# Project Name
What it is, what problem it solves, your role, tech used, outcomes.
PROJ

# GitHub READMEs — just copy them in
cp ~/code/my-project/README.md data/github/my-project.md

# Blog posts
cp my_article.md data/blog/
```

### 5. Set your contact details

```bash
export AVATAR_OWNER_NAME="Sanjana"
export AVATAR_OWNER_EMAIL="sanjana@email.com"
export AVATAR_OWNER_WHATSAPP="12125551234"   # country code + number, no spaces
```

Or create a `.env` file (add to `.gitignore`!):
```
AVATAR_OWNER_NAME=Sanjana
AVATAR_OWNER_EMAIL=sanjana@email.com
AVATAR_OWNER_WHATSAPP=12125551234
OLLAMA_MODEL=llama3.2
```

Then load it before running:
```bash
export $(cat .env | xargs)
```

### 6. Run

```bash
# Terminal 1 — keep running
ollama serve

# Terminal 2
uvicorn app:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000)

The first run builds the vector index (10–60 seconds depending on how many documents you have). Subsequent starts load from `.index_cache/` in ~2 seconds.

---

## Rebuilding the index

The index is cached. If you add, remove, or edit documents:
```bash
rm -rf .index_cache
# restart the server — index rebuilds automatically
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `AVATAR_OWNER_NAME` | `Sanjana` | Your name — appears in UI and prompts |
| `AVATAR_OWNER_EMAIL` | `your@email.com` | Where unanswered questions get sent |
| `AVATAR_OWNER_WHATSAPP` | _(blank)_ | Your number with country code — leave blank to hide the button |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `OLLAMA_MODEL` | `llama3.2` | Any model you've pulled |

---

## Embedding in a portfolio site (GitHub Pages)

```html
<iframe
  src="https://your-deployed-url.com"
  width="100%"
  height="720"
  style="border:none; border-radius:20px;"
></iframe>
```

---

## Upgrading the email feature

The `/mailto-body` endpoint currently opens the recruiter's own email client (zero server-side infra needed). To upgrade to server-side sending:

**Option A — EmailJS (no backend changes, free 200/month):**
Replace the `openMailto()` function in `index.html` with an EmailJS call using your service ID and template ID.

**Option B — SMTP via FastAPI (Gmail app password, free):**
In `app.py`, replace the `mailto-body` endpoint body with `smtplib` and `email.mime` to send directly. Store credentials in environment variables, never in code.

---

## API reference

### `POST /chat`
```json
// Request
{ "question": "What's her tech stack?" }

// Response
{ "answer": "Sanjana works primarily with...", "answered": true, "sources": ["..."] }

// When the avatar can't answer
{ "answer": "I don't have that information...", "answered": false, "sources": [] }
```

### `POST /mailto-body`
```json
// Request
{
  "recruiter_name": "Jane Smith",
  "recruiter_email": "jane@company.com",
  "recruiter_company": "Acme Corp",
  "questions": ["What's her salary expectation?", "Is she open to relocation?"]
}

// Response
{ "mailto_url": "mailto:sanjana@email.com?subject=...&body=...", "subject": "..." }
```

### `GET /config`
```json
{ "owner_name": "Sanjana", "owner_email": "...", "has_whatsapp": true, "whatsapp_number": "..." }
```

### `GET /health`
```json
{ "status": "ok", "model": "llama3.2", "ollama_reachable": true, "index_ready": true }
```

---

## What to build next

- **Conversation memory** — pass last N turns to Ollama so follow-up questions work
- **Streaming responses** — use Ollama `stream: true` + FastAPI `StreamingResponse`
- **Admin view** — a private `/admin` page showing all questions asked this session
- **Contact form logging** — store recruiter name/email to a JSON file or SQLite so you can follow up
- **Multi-language** — Ollama handles this naturally; just update the system prompt

---

## Troubleshooting

**`Cannot connect to Ollama`** → Run `ollama serve` in a separate terminal.

**`model 'llama3.2' not found`** → Run `ollama pull llama3.2`.

**Index not updating after adding files** → Delete `.index_cache/` and restart.

**Slow first response** → Normal — Ollama loads the model into RAM on first use. `llama3.2:1b` is faster if you're on limited RAM.