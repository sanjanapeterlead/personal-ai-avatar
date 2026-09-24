# Project Issues Faced and Solved

---

## Issue 8: Gemini API Key Leaked into Logs via the Request URL

**Symptom:** Every `/chat` call using Gemini printed a log line like:
```
INFO httpx — HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key=AIza... "HTTP/1.1 200 OK"
```
The full API key was visible in the terminal, and would have been stored in the
hosting provider's log dashboard after deployment.

**Cause:** Two things combined:
1. `llm.py` passed the key as a URL query parameter (`?key=...`).
2. `app.py` calls `logging.basicConfig(level=logging.INFO)`, which turns on
   INFO logs for *every* library. httpx logs each request's full URL at INFO
   (`httpx/_client.py`, `'HTTP Request: %s %s ...'`).

Nothing in our own code printed the key. A third-party library did, because
the secret was in a place libraries treat as safe to log.

**Fix:**
1. `llm.py`: send the key in the `x-goog-api-key` header, and post to the bare
   `GEMINI_API_URL` with no query string.
2. `app.py`: `logging.getLogger("httpx").setLevel(logging.WARNING)` as defense
   in depth. httpx errors still show, but routine request URLs are no longer logged.

**Verified:** Ran a real Gemini call with INFO logging captured. The answer came
back normally, the key did not appear in the logs, and no `HTTP Request` lines
were emitted.

**Why / lesson:** Secrets belong in headers, not URLs. Proxies, load
balancers, server access logs, browser history and HTTP clients all log URLs by
default, and usually don't log headers. The log-level change alone would not be
a fix. It hides this one logger, but the key would still be in the URL for any
other layer that logs it. **Follow-up:** the key was printed to local
terminals before this fix. It was never deployed, so the risk is low, but
rotating it in Google AI Studio is cheap and removes the doubt.

---

## Issue 6: LLM_PROVIDER Crashes if Not Set in .env (AttributeError)

**Error:**
```
AttributeError: 'NoneType' object has no attribute 'lower'
```

**Cause:** `os.environ.get("LLM_PROVIDER").lower()` — `.get()` returns `None` when
the variable is absent, and calling `.lower()` on `None` throws `AttributeError`.

**Fix:** Added a default value:
```python
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").lower()
```

---

## Issue 7: Monolithic app.py — All Config, Logic, and Routes in One File

**Symptom:** `app.py` was 330+ lines mixing environment reads, RAG indexing,
LLM HTTP calls, prompt building, and all five endpoints in a single file.
Env vars were not properly isolated — hard to debug, test, or extend.

**Fix:** Split into focused modules:

| Module | Responsibility |
|---|---|
| `config.py` | All `os.environ.get()` calls, path constants, startup validation |
| `schemas.py` | Pydantic request/response models |
| `indexer.py` | Document loading, chunking, embedding, index persistence |
| `prompts.py` | `SYSTEM_PROMPT` constant and `build_prompt()` |
| `llm.py` | `call_ollama`, `call_gemini`, `call_llm` (provider abstraction) |
| `routers/health.py` | `GET /health` |
| `routers/chat.py` | `POST /chat` |
| `routers/misc.py` | `GET /config`, `POST /mailto-body`, `GET /` |
| `app.py` | FastAPI instance, lifespan, middleware, router registration only |

**Why:** Each file now has one reason to change. Config is the only place that
touches environment variables — all other modules import from `config.py`.

---

## Issue 1: Port 8000 Access Denied on Windows

**Error:**
```
ERROR: [WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions
```

**Cause:** Port 8000 was already in use by another process, or blocked by Windows firewall/antivirus.

**Fix:** Run on a different port:
```powershell
venv\Scripts\uvicorn app:app --reload --port 8080
```
Or find and kill the process holding port 8000:
```powershell
netstat -ano | findstr :8000
Stop-Process -Id <PID> -Force
```

---

## Issue 2: requirements.txt Corrupted (UTF-16 LE Encoding)

**Symptom:** requirements.txt showed every character spaced out with junk bytes:
```
f a s t a p i
u v i c o r n
```

**Cause:** The file was saved by PowerShell's default encoding (UTF-16 LE with BOM). `pip install -r requirements.txt` fails silently or installs nothing.

**Fix:** Rewrite the file using the Write tool (which saves as UTF-8). Verify with:
```powershell
Get-Content requirements.txt -Encoding UTF8
```

---

## Issue 3: LLM Hallucinating When Data Files Were Empty/Template

**Symptom:** When asked "What are Sanjana's tech skills?", the model responded with fabricated details:
> "She is proficient in Python, Java, C++. Her favorite frameworks are Django and Spring."

None of this was in any document.

**Root Cause:** Two compounding problems:
1. `data/aboutMe.md` contained only placeholder template text — no real facts about Sanjana.
2. `data/Resume.pdf` produced binary/corrupted text when extracted by pypdf (likely a scanned/image-based PDF).
3. The model received garbage or template text as context, had nothing factual to return, but still generated a plausible-sounding answer using its training data instead of saying "I don't have that information".

**Attempted Fixes (partial — did not fully resolve):**
- Added `_is_meaningful()` to filter binary chunks (printable character ratio check) — filtered PDF garbage but not readable template text.
- Added `MIN_SIMILARITY = 0.40` score threshold on retrieved nodes — did not stop hallucination from template text since template text scores reasonably high against skill-related questions.
- Strengthened system prompt with "CRITICAL: do not use general knowledge" — small local models (llama3.2) do not reliably follow custom prompt instructions.

**Underlying conflict:**
The original CLAUDE.md constraint (`Settings.llm = None` — call Ollama manually) bypasses LlamaIndex's query engine, which has proven internal prompts that reliably return `"Empty Response"` on missing context. Switching to `index.as_query_engine(llm=Ollama(...))` (as the user's original working script used) fixes hallucination but conflicts with this constraint.

**Status: Resolved.** CLAUDE.md constraint #3 updated to use `Settings.llm = Ollama(...)` and `index.as_query_engine(llm=llm)`. `UNANSWERED_SIGNAL` changed to `"Empty Response"` (LlamaIndex's native signal). Manual Ollama HTTP call removed.

**Real fix (data-level):** Fill `data/aboutMe.md` with Sanjana's actual information. Re-export Resume.pdf as a text-based PDF (not scanned image). Delete `.index_cache/` and restart to rebuild the index with real content.

---

## Issue 5: Ollama Out of Memory — Model Too Large for Available RAM

**Error:**
```
Query error: model requires more system memory (11.4 GiB) than is available (6.5 GiB)
```

**Cause:** `llama3.2` (3B parameter model) requires ~11.4 GiB RAM. The machine only had 6.5 GiB free.

**Fix:** Switch to `llama3.2:1b` (1B parameter version, ~1.3 GiB RAM):
```powershell
ollama pull llama3.2:1b
```
Updated `.env`:
```
OLLAMA_MODEL=llama3.2:1b
```

**Trade-off:** The 1B model is less capable than 3B but sufficient for RAG — it's only synthesizing answers from retrieved context, not reasoning from scratch.

---

## Issue 4: App Needed Manual env Vars on Every Start

**Symptom:** Server returned placeholder values (`owner_name: "Sanjana"`, `owner_email: "your@email.com"`) unless environment variables were set manually before each run.

**Cause:** `app.py` used `os.environ.get(...)` but never loaded the `.env` file.

**Fix:** Added at the top of `app.py`:
```python
from dotenv import load_dotenv
load_dotenv()
```
The `.env` file already had the correct values. `python-dotenv` was already listed in `requirements.txt`. Now the server reads `.env` automatically on startup — no manual export needed.
