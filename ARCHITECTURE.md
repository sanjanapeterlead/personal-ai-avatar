# Architecture — Personal AI Avatar

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RECRUITER'S BROWSER                         │
│                                                                     │
│   index.html  (self-contained vanilla JS widget)                   │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │  Chat UI  │  Escalation Card  │  End Chat button             │  │
│   └────────────────────┬─────────────────────────────────────────┘  │
└────────────────────────│────────────────────────────────────────────┘
                         │  HTTP  (fetch / JSON)
                         │
┌────────────────────────▼────────────────────────────────────────────┐
│                      FASTAPI BACKEND  (app.py)                      │
│                                                                     │
│  POST /chat          GET /health        GET /config                 │
│  POST /mailto-body   GET /                                          │
│                                                                     │
│  ┌──────────────┐   ┌─────────────┐   ┌──────────────────────────┐ │
│  │ routers/     │   │ indexer.py  │   │ llm.py                   │ │
│  │  chat.py     │──▶│             │   │                          │ │
│  │  health.py   │   │ Loads docs  │   │  call_llm()              │ │
│  │  misc.py     │   │ Chunks text │   │    ├── call_ollama()     │ │
│  └──────┬───────┘   │ Embeds      │   │    └── call_gemini()     │ │
│         │           │ Persists    │   └───────────┬──────────────┘ │
│         │           └──────┬──────┘               │                │
│  ┌──────▼───────┐          │          ┌────────────▼─────────────┐ │
│  │ prompts.py   │   ┌──────▼──────┐   │   LLM_PROVIDER (env)    │ │
│  │              │   │ app.state   │   │   "ollama" or "gemini"  │ │
│  │ SYSTEM_PROMPT│   │ .retriever  │   └────────────┬────────────┘ │
│  │ build_prompt │   └─────────────┘                │               │
│  └──────────────┘                                  │               │
│                                                    │               │
│  ┌─────────────┐   ┌──────────────┐                │               │
│  │ schemas.py  │   │  config.py   │◀───── .env ────┘               │
│  │             │   │              │                                 │
│  │ ChatRequest │   │ all env vars │                                 │
│  │ ChatResponse│   │ validation   │                                 │
│  └─────────────┘   └──────────────┘                                │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
              ┌───────────────────┴──────────────────┐
              │                                      │
┌─────────────▼──────────────┐       ┌───────────────▼──────────────┐
│   OLLAMA  (local process)  │       │  GEMINI API  (Google cloud)  │
│                            │       │                              │
│  llama3.2:1b (or any model)│       │  gemini-1.5-flash            │
│  POST /api/generate        │       │  free: 15 RPM, 1M tok/day    │
│  runs on your machine      │       │  needs GEMINI_API_KEY        │
└────────────────────────────┘       └──────────────────────────────┘
```

---

## 2. Module Dependency Graph

```
         .env
          │
          ▼
      config.py          ◀── single source of truth for all env vars
      │  │  │  │
      │  │  │  └──────────────────────────────┐
      │  │  └───────────────────┐             │
      │  └──────────┐           │             │
      │             │           │             │
      ▼             ▼           ▼             ▼
  indexer.py    prompts.py   llm.py       schemas.py
      │             │           │             │
      │             └─────┐     │             │
      │                   ▼     ▼             │
      │              routers/chat.py ◀────────┘
      │              routers/health.py
      │              routers/misc.py ◀─── schemas.py
      │
      └──────────────────────────────────────────▶ app.py
                                                  (wires everything)
```

**Rule:** arrows point toward dependencies. `config.py` has no internal
imports — it only reads from the environment. Everything else imports
from `config.py`, never directly from `os.environ`.

---

## 3. /chat Request Flow (the critical path)

```
Browser sends: POST /chat  {"question": "What are her skills?"}
                │
                ▼
        routers/chat.py
                │
                ├─1─ validate: question not empty
                │
                ├─2─ get retriever from app.state
                │         (set during startup by lifespan in app.py)
                │
                ├─3─ retriever.retrieve(question)          [asyncio.to_thread]
                │         │
                │         ▼
                │    LlamaIndex VectorStoreIndex
                │    cosine-similarity search over
                │    embedded chunks in .index_cache/
                │    returns top-6 NodeWithScore objects
                │
                ├─4─ nodes empty?
                │         YES ──▶ return answered=False  (escalation card)
                │         NO  ──▶ continue
                │
                ├─5─ build_prompt(question, context_chunks)
                │         │
                │         ▼
                │    prompts.py: SYSTEM_PROMPT + CONTEXT + QUESTION
                │
                ├─6─ call_llm(prompt)
                │         │
                │         ├── LLM_PROVIDER="ollama"
                │         │       └── POST http://localhost:11434/api/generate
                │         │
                │         └── LLM_PROVIDER="gemini"
                │                 └── POST generativelanguage.googleapis.com
                │
                ├─7─ answer.startswith("I don't have that information")?
                │         YES ──▶ answered=False  (escalation card)
                │         NO  ──▶ answered=True
                │
                └─8─ return ChatResponse(answer, answered, provider, sources)
```

---

## 4. Startup / Index Build Flow

```
uvicorn starts app.py
        │
        ▼
   lifespan()
        │
        ├── indexer.build_index()
        │       │
        │       ├── .index_cache/ exists?
        │       │       YES ──▶ load_index_from_storage()  [fast, ~2s]
        │       │       NO  ──▶ collect_documents()
        │       │                   │
        │       │                   ├── look for data/resume/, data/bio/ …
        │       │                   └── fallback: read data/ flat
        │       │               SentenceSplitter(chunk_size=600, overlap=80)
        │       │               HuggingFaceEmbedding(all-MiniLM-L6-v2)
        │       │               VectorStoreIndex(nodes)
        │       │               persist to .index_cache/     [slow, ~30–60s]
        │       │
        │       └── returns VectorStoreIndex
        │
        ├── app.state.retriever = index.as_retriever(top_k=6)
        │
        └── server ready — accepts requests
```

---

## 5. Escalation Flow (unanswered questions)

```
answered=False returned by /chat
        │
        ▼
  index.html (frontend)
        │
        ├── unansweredList.push(question)     [in-memory, session only]
        │
        ├── show escalation card (Email / WhatsApp buttons)
        │
        └── show amber banner: "N questions couldn't be answered"

User clicks "End Chat" OR "Email Sanjana"
        │
        ▼
  POST /mailto-body  { questions: unansweredList, recruiter_name, … }
        │
        ▼
  routers/misc.py builds mailto: URL
        │
        ▼
  window.location.href = mailto:...
        │
        ▼
  Recruiter's email client opens with pre-filled message to Sanjana
  (nothing sent server-side — client-only flow)
```

---

## 6. Design Choices Explained

### Why LlamaIndex only for embeddings + retrieval, not LLM?

LlamaIndex's built-in LLM integration works well for single-provider setups
but makes multi-provider switching harder. By calling Ollama and Gemini
directly via `httpx`, swapping providers is a single env var change with no
library coupling. `Settings.llm = None` keeps LlamaIndex in its lane
(chunking, embedding, vector search).

### Why HuggingFace `all-MiniLM-L6-v2` for embeddings?

- Runs fully locally — no API key, no cost, no data leaving the machine
- 384-dimension vectors, fast on CPU
- Good general-purpose semantic similarity for English text
- Small enough to embed on startup without GPU

**Trade-off:** Larger models (e.g. `bge-large-en`) give better recall but
need more RAM and are slower to embed.

### Why persist the index to `.index_cache/`?

Embedding 100+ document chunks takes 30–60 seconds on CPU. Persisting the
index means every restart after the first loads in ~2 seconds. The cache is
intentionally gitignored — it is derived from `data/` and can always be
rebuilt by deleting the folder.

### Why `chunk_size=600, chunk_overlap=80`?

- Resume PDFs and JSON bios have dense, information-rich sentences
- 600 chars ≈ 3–4 sentences — enough context for the LLM without exceeding
  the retriever's useful window
- 80-char overlap ensures a sentence split at a chunk boundary doesn't lose
  its context

### Why `top_k=6`?

With multiple document types (resume, bio, projects, blog, GitHub READMEs),
a question about "projects" might retrieve chunks from several files.
`top_k=6` gives the LLM enough diversity to synthesise a full answer without
overloading the context window.

### Why `answered: bool` in ChatResponse?

The frontend cannot reliably parse free-text LLM output to decide whether to
show the escalation card. A server-side boolean is authoritative and version-
stable. The check (`answer.startswith(UNANSWERED_SIGNAL)`) lives in one
place — `routers/chat.py` — and is driven by a single constant in
`config.py`.

### Why client-side mailto instead of server-side email?

- No SMTP credentials, no email service cost, no spam risk
- Works with any email client the recruiter already uses
- Zero server state — the backend stays stateless
- Can be upgraded to server-side (SendGrid / SMTP) by replacing only the
  `/mailto-body` endpoint body, with no frontend changes

### Why a `routers/` package instead of one flat `routes.py`?

Each router has one clear job. Adding a new endpoint group (e.g.
`/analytics`, `/feedback`) means adding a new file and one
`app.include_router()` line, with no risk of touching unrelated endpoints.

---

## 7. Key Concepts Explained

### RAG — Retrieval-Augmented Generation

RAG is the core pattern this project is built on. Instead of asking an LLM to answer from memory (which leads to hallucination), you first **retrieve** the relevant facts from your own documents and then **augment** the LLM's prompt with those facts.

```
Without RAG:   Question ──────────────────────▶ LLM ──▶ Answer (from training data)
                                                         ↑ may hallucinate

With RAG:      Question ──▶ Vector Search ──▶ Relevant chunks
                                                    │
                                                    ▼
               Question + chunks ──────────▶ LLM ──▶ Grounded answer
                                                         ↑ based only on your docs
```

The LLM's job shrinks from "know everything" to "summarise what I give you." This is why even a small local model (llama3.2:1b) can give accurate answers about Sanjana — it never has to invent facts.

---

### Vector Embeddings

An embedding is a list of numbers (a vector) that represents the *meaning* of a piece of text. Sentences with similar meanings produce vectors that are close together in space, regardless of exact wording.

```
"What are her skills?"        → [0.12, -0.45, 0.88, …]  (384 numbers)
"Which technologies does she know?" → [0.11, -0.43, 0.85, …]  (very close)
"What is her favourite food?"  → [0.62,  0.21, -0.33, …] (far away)
```

This project uses HuggingFace's `sentence-transformers/all-MiniLM-L6-v2` to produce these vectors. It runs locally — no API key, no data sent anywhere. Every document chunk and every incoming question gets embedded the same way so they can be compared.

---

### Vector Store and the Index Cache

A vector store is a database of embeddings. When you ask a question:
1. The question is embedded into a vector
2. The store finds the stored chunk vectors closest to it (cosine similarity)
3. Those chunks are returned as context

This project uses LlamaIndex's `VectorStoreIndex`, which saves the index to `.index_cache/` on disk. This means:
- **First startup:** embed all chunks → takes 30–60 seconds → save to disk
- **Every restart after:** load from disk → takes ~2 seconds → ready

Delete `.index_cache/` any time you add new documents so the index is rebuilt with the new content.

---

### Chunking and Chunk Overlap

LLMs have a limit on how much text they can read at once (the context window). A 10-page resume can't be fed in whole. Instead, documents are split into smaller pieces called **chunks**, and only the most relevant chunks are sent to the LLM.

```
Original document (5000 chars):
┌──────────────────────────────────────────────────────┐
│  [chunk 1: 600 chars] [chunk 2: 600 chars] [chunk 3…]│
└──────────────────────────────────────────────────────┘
         └── 80-char overlap ──┘
```

The **overlap** ensures that a sentence split across two chunk boundaries isn't lost — the end of chunk 1 repeats at the start of chunk 2. This project uses `chunk_size=600, chunk_overlap=80`, tuned for resume and bio text.

---

### Cosine Similarity

This is how the vector store decides which chunks are "most relevant" to a question. It measures the angle between two vectors — not their length, just their direction.

- Score of **1.0** = identical meaning
- Score of **0.0** = completely unrelated
- Score of **-1.0** = opposite meaning (rare in practice)

The retriever returns the top 6 chunks with the highest cosine similarity to the question. This is why asking "Python experience?" surfaces the same chunks as "Does she know backend development?" — both questions point in the same semantic direction.

---

### LlamaIndex

LlamaIndex is a framework for building RAG pipelines. This project uses it for exactly three things:

| Task | LlamaIndex tool used |
|---|---|
| Load documents (PDF, MD, JSON, TXT) | `SimpleDirectoryReader` |
| Split into chunks | `SentenceSplitter` |
| Embed, store, and search | `VectorStoreIndex` + `as_retriever()` |

It is deliberately **not** used for LLM calls. `Settings.llm = None` tells LlamaIndex to do retrieval only. The actual Ollama HTTP call is made manually in `llm.py`, giving full control over the prompt format and provider switching.

---

### FastAPI Lifespan

FastAPI's lifespan is a startup/shutdown hook that runs once when the server starts and once when it stops. It is the right place for expensive one-time setup like building the vector index.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # runs once on startup
    index = build_index()
    app.state.retriever = index.as_retriever(similarity_top_k=6)
    yield          # server is live here, handling requests
    # runs once on shutdown (cleanup goes here)
```

The `yield` separates startup code (above) from shutdown code (below). Everything before `yield` runs before the first request is accepted.

---

### app.state — Sharing Objects Across Requests

FastAPI provides `app.state` as a place to store objects that need to be shared across all requests without using global variables. The retriever is expensive to build (it loads the entire index into memory), so it's built once at startup and stored here.

```python
# set once at startup (lifespan):
app.state.retriever = index.as_retriever(...)

# read on every request (routers/chat.py):
retriever = request.app.state.retriever
```

This is safer than a module-level global because FastAPI manages the lifecycle — if startup fails, the server never starts and the state is never set.

---

### asyncio.to_thread

FastAPI is asynchronous — it handles many requests concurrently on a single thread using Python's `asyncio` event loop. LlamaIndex's `retriever.retrieve()` is a regular synchronous (blocking) function. If called directly, it would block the event loop and freeze all other requests while it runs.

`asyncio.to_thread()` runs a synchronous function in a separate worker thread so the event loop stays free:

```python
nodes = await asyncio.to_thread(retriever.retrieve, question)
#       ↑ event loop free      ↑ runs in thread pool
```

The `await` suspends this request handler until the thread finishes, but other requests can still be handled in the meantime.

---

### UNANSWERED_SIGNAL — The Escalation Contract

The signal phrase `"I don't have that information"` is the contract between the LLM, the backend, and the frontend. It works as follows:

1. `prompts.py` instructs the LLM: *if context is insufficient, start your answer with this exact phrase*
2. `routers/chat.py` checks `answer.startswith(UNANSWERED_SIGNAL)` → sets `answered = False`
3. `index.html` reads `answered` from the JSON response → shows the escalation card

The phrase is defined once in `config.py` as `UNANSWERED_SIGNAL` and imported by both `prompts.py` and `routers/chat.py`. Changing it in one place automatically updates both. The frontend never inspects the answer text — it only reads the boolean `answered` field.

---

### python-dotenv and the .env File

Environment variables are the standard way to pass secrets and configuration to a server without putting them in source code. `python-dotenv` reads a `.env` file and loads its contents into `os.environ` at startup.

```
.env file (gitignored, never committed):        config.py reads:
AVATAR_OWNER_NAME=Sanjana           →   OWNER_NAME = os.environ.get("AVATAR_OWNER_NAME")
OLLAMA_MODEL=llama3.2:1b            →   OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL")
```

`load_dotenv()` is called once at the top of `config.py`. All other modules import constants from `config.py` — they never call `os.environ` directly. This means there is exactly one place to look if an environment variable is missing or wrong.

---

### Pydantic Models — Request and Response Validation

Pydantic automatically validates the shape of incoming JSON and outgoing responses. If a request is missing a required field or has the wrong type, FastAPI returns a `422 Unprocessable Entity` error before the handler code even runs.

```python
class ChatRequest(BaseModel):
    question: str          # required — missing this → 422 automatically

class ChatResponse(BaseModel):
    answer:   str
    answered: bool         # load-bearing: frontend uses this for escalation card
    provider: str
    sources:  list[str] = []   # optional, defaults to empty list
```

The `answered: bool` field is particularly important — it is a typed contract between the backend and frontend. Renaming or removing it would silently break the escalation card.

---

### The mailto: Escalation Flow (Client-Side Email)

When a question can't be answered, the frontend shows a card offering to email Sanjana. The backend builds a pre-filled `mailto:` URL — a browser-native link that opens the user's own email client with the subject and body already filled in.

```
POST /mailto-body  →  backend builds:
mailto:sanjana@email.com?subject=Questions...&body=Hi Sanjana,...

window.location.href = that URL  →  recruiter's email client opens
```

No email is sent server-side. No SMTP credentials are needed. The recruiter reviews the pre-filled message and clicks Send themselves. This keeps the backend completely stateless and avoids all spam and authentication concerns.

---

## 8. Improvements Still Needed

### HIGH PRIORITY

| # | Issue | Impact | Suggested Fix |
|---|---|---|---|
| 1 | **No conversation memory** | Each question is answered in isolation — the LLM has no context of what was asked earlier in the session | Pass last 3–5 message pairs as `chat_history` in the prompt |
| 2 | **Unanswered list lost on refresh** | `unansweredList` lives in JS memory — page refresh loses all captured questions | Save to `localStorage` in `index.html`; clear on End Chat |
| 3 | **No streaming responses** | The LLM generates the full answer before anything appears — feels slow for long answers | Use Ollama's `stream: true` + Gemini's streaming API with FastAPI `StreamingResponse` |
| 4 | **PDF text extraction not validated** | If a PDF is scanned (image-only), `pypdf` returns empty text silently — the chunk is indexed as blank and retrieved as garbage | On index build, log a warning when a loaded document has < 50 chars; suggest OCR |

### MEDIUM PRIORITY

| # | Issue | Impact | Suggested Fix |
|---|---|---|---|
| 5 | **No re-ranking** | The retriever returns the top-6 by cosine similarity, but similarity ≠ relevance for short questions | Add a cross-encoder re-ranker (e.g. `ms-marco-MiniLM-L-6-v2`) after retrieval |
| 6 | **Index rebuild requires server restart** | Adding a new document to `data/` requires deleting `.index_cache/` and restarting | Add a `POST /rebuild-index` admin endpoint (protected by a secret header) |
| 7 | **No rate limiting** | The `/chat` endpoint can be called in a tight loop — will exhaust Gemini's free 15 RPM quota or overload local Ollama | Add `slowapi` rate limiter: e.g. 20 req/min per IP |
| 8 | **Gemini API key in `.env` plain text** | Key is readable by anyone with filesystem access | Use OS keychain or a secrets manager (e.g. `python-keyring`, AWS Secrets Manager) for production |

### LOW PRIORITY / NICE TO HAVE

| # | Issue | Impact | Suggested Fix |
|---|---|---|---|
| 9 | **No automated tests** | Refactors have no safety net | Add `pytest` + `httpx.AsyncClient` integration tests for each endpoint |
| 10 | **Single data folder, flat fallback** | Files in `data/` root (not subdirs) trigger the fallback path silently | Enforce the sub-folder structure and log a clear warning if flat fallback is used |
| 11 | **Gemini response capped at 600 tokens** | Long project descriptions get cut off mid-sentence | Make `maxOutputTokens` a config constant; raise to 1200 for Gemini (free tier allows it) |
| 12 | **No feedback loop** | There is no way to know which answers were good or bad without reading the emails | Add a 👍/👎 button per message; log to a local SQLite file for review |
| 13 | **`index.html` title is hard-coded** | "Chat with Sanjana's Avatar" is in `<title>` — `/config` already returns `owner_name` but the page title is not updated dynamically | One-line JS fix: `document.title = \`Chat with \${name}'s Avatar\`` (already done in the init block — verify it works) |
