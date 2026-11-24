# LLM Chatbot with Key Failover and Response Caching

React + FastAPI + SQLite chatbot. LiteLLM provides the key pool with automatic failover and the response cache. Every AI reply shows its resolution source, model, latency and per-request token usage.

## 1. Live URLs

| | URL |
|---|---|
| Frontend | _TODO: Vercel URL_ |
| Backend | _TODO: Render URL_ |
| Backend health | _TODO: Render URL_/health |
| Repository | _TODO: GitHub URL_ |

The backend runs on Render's free tier, which sleeps when idle. The first request after a pause can take about 30 to 60 seconds. Open `/health` first to wake it.

## 2. Run locally

### With Docker (the way graders run it)

```bash
cp .env.example .env     # then put real keys in LLM_API_KEYS (make up does the copy if .env is missing)
make up                  # backend http://localhost:8000, frontend http://localhost:3000
make down                # stop; the named volume keeps the SQLite history
```

`make logs` tails both services and `make test` runs the backend tests.

### Without Docker

Backend (Python 3.12):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../.env.example .env                              # edit keys; DATABASE_URL=sqlite:///./data/app.db works locally
uvicorn app.main:app --reload --port 8000
```

Frontend (Node 20+):

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev       # http://localhost:3000
```

### Environment variables

| Variable | Meaning |
|---|---|
| `LLM_API_KEYS` | Comma-separated key pool, at least 2. Ids are `key_1`, `key_2`, ... in order. |
| `LLM_MODEL` | LiteLLM model used by every key unless `LLM_MODELS` says otherwise. |
| `LLM_MODELS` | Optional, one model per key in key order, so the pool can span providers (for example Groq then Gemini). |
| `DATABASE_URL` | SQLite location, for example `sqlite:////data/app.db`. |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins. |
| `ENABLE_FAILURE_SIMULATION` | `true` enables the `X-Simulate-Failure` header. |
| `LLM_TIMEOUT_SECONDS` | Per-key call timeout before failing over (default 30). |
| `CACHE_TTL_SECONDS` | Lifetime of cached responses (default 3600). |
| `VITE_API_URL` | Frontend build-time backend URL. |

## 3. Design decisions

### Key fallback

`backend/app/llm.py` walks the key pool in order (`key_1`, `key_2`, ...) and calls `litellm.acompletion` once per key.

- Any provider failure moves on to the next key: HTTP 429, quota errors, 5xx, timeouts, auth errors, and empty replies.
- An explicit loop gives exact `key_id` and `fallback_attempts` values, which the API contract requires. LiteLLM Router hides those details.
- Same-key retries are turned off (`num_retries=0`), so a failing key costs one attempt.
- Each call has a timeout, so a hung provider cannot block the request.
- Every key can use its own model (`LLM_MODELS`). In this deployment `key_1` is Groq and `key_2` is Gemini. If one provider is down, the other still answers.
- If every key fails, the API returns `503 {"detail": "all providers unavailable"}`, and nothing is written to history. Keys are never returned or logged. Only `key_id` appears.

### Caching

LiteLLM's built-in in-memory cache (`litellm.cache = Cache(type="local")`) is enabled at startup. LiteLLM derives the cache key from the model and the full message list: system prompt, history and new message. It does not include the API key, so a reply cached through `key_2` is still a hit when `key_1` is tried first.

- A hit returns the identical reply text and the usage stored with it. The API reports `LLM_CACHE`, `key_id: null` and `fallback_attempts: 0`.
- The same first message in a new session is a hit. A different message, a different history or a different system prompt is a different key, so it is a live call.
- LiteLLM writes cache entries in a background task, so the client yields briefly after a live call (excluded from `latency_ms`). That makes an immediate repeat a hit.
- LiteLLM 1.110 no longer ships a disk cache backend, so the cache is in-memory. It resets when the container restarts. Session history is separate and persistent.
- When `X-Simulate-Failure` is present, the cache is bypassed. Otherwise `*=429` on an already-cached prompt would return a cache hit instead of the expected 503.

### SQLite session storage

- `messages` follows the specified schema, plus an index on `(session_id, id)` and a small `sessions` table that remembers a session's system prompt.
- The schema is created on startup. `DATABASE_URL` points at the file, which lives on the `appdata` Docker volume at `/data`, so history survives `make down && make up`.
- A request's user and assistant rows plus the session row are written in one transaction, and only after a successful LLM call. A 422 or 503 leaves no trace in history.
- A per-session `asyncio.Lock` serialises requests inside one session so history cannot interleave.
- Each assistant row stores its metadata as JSON, and `GET /sessions/{id}/messages` returns it.

### Other decisions

- Tokens come from the provider's `usage` for this one call, never a running total. If a provider omits usage, LiteLLM's token counter provides an estimate.
- `latency_ms` is measured with `time.perf_counter()` around the key loop, so it includes failed attempts and cache lookups.
- Errors are always JSON `{"detail": ...}`. A catch-all handler hides stack traces behind `{"detail": "internal server error"}`.
- Docker images are multi-stage. The backend runs as a non-root user.

## 4. Verification

Replace `$API` with `http://localhost:8000` or the live backend URL.

```bash
API=http://localhost:8000
curl $API/health
# {"status":"ok","keys_configured":2,"cache_enabled":true}
```

**Per-message token usage.** Each `/chat` response carries `metadata.input_tokens` and `output_tokens` for that request only. In the UI they sit beside every reply.

```bash
curl -s -X POST $API/chat -H 'content-type: application/json' \
  -d '{"session_id":"demo-1","message":"What is the capital of France?"}'
```

**Cache hit.** Send the same message from a new session. The reply text is identical, `resolution_source` is `LLM_CACHE`, `key_id` is `null`, and `latency_ms` is much lower.

```bash
curl -s -X POST $API/chat -H 'content-type: application/json' \
  -d '{"session_id":"demo-2","message":"What is the capital of France?"}'
```

**Failover** (needs `ENABLE_FAILURE_SIMULATION=true`):

```bash
# key_1 fails with 429, key_2 answers -> 200, "key_id":"key_2","fallback_attempts":1
curl -s -X POST $API/chat -H 'content-type: application/json' -H 'X-Simulate-Failure: key_1=429' \
  -d '{"session_id":"demo-3","message":"Tell me a fun fact"}'

# every key fails -> 503 {"detail":"all providers unavailable"}, nothing stored
curl -s -i -X POST $API/chat -H 'content-type: application/json' -H 'X-Simulate-Failure: *=429' \
  -d '{"session_id":"demo-4","message":"hello"}'
curl -s -i $API/sessions/demo-4/messages        # 404 session not found
```

**Multi-turn and history.**

```bash
curl -s -X POST $API/chat -H 'content-type: application/json' -d '{"session_id":"demo-5","message":"My name is Sam"}'
curl -s -X POST $API/chat -H 'content-type: application/json' -d '{"session_id":"demo-5","message":"What is my name?"}'
curl -s $API/sessions/demo-5/messages           # oldest first, assistant rows carry metadata
```

**Validation.** An empty message, a message over 4000 characters, a missing `session_id` or malformed JSON returns 422 with a `detail` field.

In the UI, open "Session settings" to pick a failure simulation from a dropdown. It sends the same `X-Simulate-Failure` header.

**Tests.** `make test` (or `cd backend && pytest`) runs 48 tests against a local fake OpenAI-compatible server, so LiteLLM's real cache and failure handling are exercised. They cover failover (simulated and real 429/500), 503 with nothing stored, cache hits and misses, per-request tokens, multi-turn context, session isolation, persistence across restarts and CORS.

## 5. Setup Used

- Editor / agent: Claude Code (CLI), model Claude Sonnet 5.5.
- LLM providers through LiteLLM: Groq (`groq/openai/gpt-oss-20b`) as `key_1` and Google Gemini as `key_2`.
- Stack: Python 3.12, FastAPI, LiteLLM, SQLite, React 19 with Vite, Docker Compose.
- Hosting: Render (backend, Docker) and Vercel (frontend).

## 6. Bonus features

- A model per key (`LLM_MODELS`), so failover can cross providers (Groq to Gemini), not just across keys on one provider.
- A system prompt field, stored per session on the backend.
- A "Simulate key failure" dropdown in the UI, so failover can be demonstrated without curl.
- Cache and live badges, a "New chat" button, a typing indicator, and readable error bubbles for 422, 503 and network failures.
- Per-key health surfaced as `key_id` and `fallback_attempts` on every reply.
