# Personal AI Avatar

An AI assistant that represents you to recruiters — answers questions about your background using your own documents, and gracefully escalates to you when it can't.

**Stack:** Ollama (local, free) or Gemini (free tier) for the LLM · HuggingFace embeddings · FastAPI · vanilla JS widget

---

## What it does

- Answers recruiter questions from your actual documents (resume, bio, projects, blog posts, GitHub READMEs)
- Detects when it can't answer and shows an escalation card with a direct email button
- Posts unanswered questions to a Slack channel in real time (Incoming Webhook — optional, no bot setup required) so you find out the moment a recruiter hits a gap, without waiting for them to send anything
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
Ollama (local) or Gemini (cloud) ← LLM_PROVIDER picks which
   system prompt + context + question
       │
       ▼
FastAPI /chat  →  { answer, answered: bool }
       │
   if answered=false:
       ├── escalation card in UI
       ├── Slack Incoming Webhook  →  real-time alert in your channel (optional)
       └── /mailto-body  →  opens recruiter's email client
                             with all unanswered questions pre-filled
```

---

## Folder structure

```
personal-ai-avatar/
├── app.py              ← FastAPI backend
├── slack.py            ← Slack Incoming Webhook notifier (optional escalation channel)
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

### 1. Pick an LLM provider

`.env.example` defaults to `LLM_PROVIDER=gemini` — the quickest way to get running,
since it needs no local install. Ollama is the alternative if you'd rather keep
everything on your own machine and avoid a cloud dependency.

**Option A — Gemini (default, no local install):**
```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key-here   # free at https://aistudio.google.com/app/apikey
```
Skip straight to step 3.

**Option B — Ollama (fully local):**
```
LLM_PROVIDER=ollama
```
Then install Ollama and pull a model:

**macOS / Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```
**Windows:** [ollama.com/download](https://ollama.com/download)

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
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key-here
```

Then load it before running:
```bash
export $(cat .env | xargs)
```

### 6. (Optional) Enable Slack notifications

Get notified in Slack the instant a recruiter asks something the avatar can't answer:

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**.
2. Pick the workspace, then open **Incoming Webhooks** in the left sidebar and toggle it on.
3. Click **Add New Webhook to Workspace**, choose the channel to post to, and authorize.
4. Copy the generated webhook URL (`https://hooks.slack.com/services/...`) into `.env`:
   ```
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
   ```

That's it — no bot token, no signing secret, no public URL needed. Treat the webhook URL as a
secret: anyone with it can post to your channel, so it only ever lives in `.env` (gitignored),
never in code or in the frontend. Leave it blank to skip Slack entirely; the app works the same
either way, just without the real-time alert.

### 7. Run

If you're using Ollama, start it first and keep it running:
```bash
ollama serve
```
(Skip this if `LLM_PROVIDER=gemini` — there's nothing local to start.)

```bash
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
| `LLM_PROVIDER` | `gemini` | `gemini` or `ollama` |
| `GEMINI_API_KEY` | _(none)_ | Required when `LLM_PROVIDER=gemini` — free at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| `GEMINI_MODEL` | `gemini-2.0-flash-lite` | Any Gemini model your key has access to |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `OLLAMA_MODEL` | `llama3.2` | Any model you've pulled |
| `SLACK_WEBHOOK_URL` | _(blank)_ | Incoming Webhook URL — leave blank to disable Slack alerts |

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
{ "question": "What's her tech stack?", "session_id": "a1b2c3d4-..." }
// session_id is optional — a per-browser-session UUID the frontend generates so
// multiple unanswered questions from the same recruiter group together in Slack

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
// LLM_PROVIDER=ollama
{ "status": "ok", "provider": "ollama", "provider_ready": true, "index_ready": true, "available_models": ["llama3.2"] }

// LLM_PROVIDER=gemini
{ "status": "ok", "provider": "gemini", "provider_ready": true, "index_ready": true, "model": "gemini-2.0-flash-lite" }
```

---

## What to build next

- **Conversation memory** — pass last N turns to Ollama so follow-up questions work
- **Streaming responses** — use Ollama `stream: true` + FastAPI `StreamingResponse`
- **Admin view** — a private `/admin` page showing all questions asked this session
- **Contact form logging** — store recruiter name/email to a JSON file or SQLite so you can follow up
- **Multi-language** — Ollama handles this naturally; just update the system prompt
- **Live two-way Slack relay** — today Slack is notify-only (you find out, then follow up via
  Email/WhatsApp). A full live relay where your Slack replies stream back into the recruiter's
  chat widget needs a Slack app with a bot token + Events API subscription, a publicly reachable
  HTTPS URL for Slack to call back into (e.g. a deployed host or an `ngrok` tunnel during dev),
  and server-side state mapping each `session_id` to a Slack thread. Bigger lift — worth doing
  once the app is actually deployed somewhere with a stable public URL.

---

## Troubleshooting

**`Cannot connect to Ollama`** → Run `ollama serve` in a separate terminal.

**`model 'llama3.2' not found`** → Run `ollama pull llama3.2`.

**Index not updating after adding files** → Delete `.index_cache/` and restart.

**Slow first response** → Normal — Ollama loads the model into RAM on first use. `llama3.2:1b` is faster if you're on limited RAM.

**`LLM_PROVIDER=gemini requires GEMINI_API_KEY`** → Set `GEMINI_API_KEY` in `.env`, or switch to `LLM_PROVIDER=ollama` if you'd rather run locally.

**Gemini `429` rate limit errors** → The free tier caps requests per minute; `llm.py` already throttles outgoing calls, but heavy simultaneous traffic can still hit the cap. Wait a few seconds and retry.

**Slack messages not arriving** → Confirm `SLACK_WEBHOOK_URL` is set and the app was restarted after editing `.env`. Failures are logged server-side (`slack.py` never raises, so the recruiter's chat keeps working either way) — check the server logs for `Slack notification failed`.

**`Router.__init__() got an unexpected keyword argument 'on_startup'`** → A `fastapi`/`starlette` version mismatch in your environment (this happens if something outside `requirements.txt` pulled in an incompatible `starlette`). Fix with `pip install --upgrade --force-reinstall fastapi starlette` inside your virtualenv.

## License

MIT