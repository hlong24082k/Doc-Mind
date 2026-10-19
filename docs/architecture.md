# Architecture Context

## Stack

| Layer        | Technology                                     | Role                                                     |
| ------------ | ---------------------------------------------- | -------------------------------------------------------- |
| Backend      | FastAPI + Python 3.11 (uv)                     | Async REST API under `/api`, SSE streaming               |
| Frontend     | React 18 + TypeScript + Vite                   | SPA: login/signup, documents, chat                       |
| UI           | Tailwind + shadcn/ui (Radix) + Lucide          | Components and HSL CSS-variable theme                    |
| Client state | Zustand + React Router                         | Auth store, protected routes                             |
| Auth         | OAuth2 password flow + JWT (python-jose), Argon2 | Login issues bearer token, `get_current_user` dependency |
| Database     | PostgreSQL 17 (ParadeDB image) + SQLAlchemy 2 async (asyncpg) | Users, documents, chunks                    |
| Migrations   | Alembic                                        | Sole owner of schema (no `create_all`)                   |
| Vector / BM25 | pgvector HNSW + ParadeDB `pg_search`          | Dense + sparse retrieval inside Postgres                 |
| LLM          | Any OpenAI-compatible Chat Completions endpoint (`openai` SDK, `AsyncOpenAI`); default Gemini `gemini-3.5-flash-lite` via OpenAI-compat | Answer generation + query rewrite, stream / non-stream |
| Embedding    | Gemini `gemini-embedding-2` (768-d)            | Chunk and query vectors                                  |
| Parsing      | PyMuPDF + HF `tokenizers` (ModernBERT)         | PDF → blocks → token-bounded chunks                      |
| Deploy       | Docker Compose: `postgres`, `server` (uvicorn, 1 process), `nginx` (built SPA + `/api` reverse proxy) | Full stack on `http://localhost` |

## System Boundaries

- `client/src/api` — HTTP layer: `apiFetch`, endpoint URLs (`config.ts`), services, response types.
- `client/src/pages`, `components`, `store` — views, shadcn UI, Zustand auth state; no direct `fetch`.
- `server/app/routers` — HTTP endpoints (auth, document, conversation, heartbeat); thin, delegate to cruds/core. Upload pre-checks in `document/limits.py`, chat limiter + SSE stream in `conversation/`.
- `server/app/cruds` — ORM CRUD (users, documents, conversations); request `AsyncSession` or a session factory for short sessions.
- `server/app/models`, `alembic/` — ORM models and the migrations that define the real schema.
- `server/app/core` — RAG engine, framework-agnostic: ingestion, embedding, storage repos, retrieval, generation, LLM. Depends only on `interfaces.py` Protocols.
- `server/app/core/factory.py` — composition root; the only core file that reads `settings`.
- `server/app/core/ingestion/worker.py` — ingest worker over the Postgres queue (in the API lifespan or `scripts/ingest_worker.py`).
- `server/scripts` — `rag_cli.py` (ingest/search/ask/eval), `ingest_worker.py`, `load_chat.py`, `seed.py`, run script.
- `server/tests/core`, `server/tests/api` — unit tests with fakes (no DB / Gemini).
- `nginx/` — image that builds the client (`VITE_API_BASE_URL=/api`) and serves it; proxies `/api/` to `server:8000` with buffering off (SSE) and `client_max_body_size` ≥ `UPLOAD_MAX_REQUEST_MB`. `server/Dockerfile` runs `alembic upgrade head` then uvicorn.

## Storage Model

- **PostgreSQL**: `users`; `documents` (owner, canonical `name` unique on `(user_id, lower(name))`, status `pending|processing|indexed|failed`, `content_hash`, counts, error, queue columns `attempts` / `claimed_at`, `size_bytes` for quota); `document_chunks` (content, section, pages, `overlap_chars`, `vector(768)` embedding, denormalized `user_id`) with HNSW and BM25 indexes; `conversations` (owner, title, `document_ids` array of 1..10); `messages` (role, content, `standalone_query`, `sources` JSONB, grounded/refused, `timings_ms`).
- **Local disk (`DOCUMENTS_FOLDER`)**: uploaded files at `{user_id}/{name}.pdf` (name canonicalized: NFC, forbidden chars → `_`, ≤ 200 bytes); `TMPDIR` should sit on the same volume for multipart spooling. Per-user quota on bytes and document count.
- **Browser localStorage**: `access_token`, `token_type`, `isLoggedIn`.

## Auth and Access Model

- Users register/login via `/api/auth`; login returns a JWT (`sub` = username), sent as `Bearer` header.
- Every document and chunk has a single owner (`user_id`); no sharing/collaborators.
- Every route under `/api` except `auth/*` and `heartbeat/*` requires `get_current_user` and filters by owner; other users' resources return 404 (enforced by `tests/api/test_auth_required.py`).
- Retrieval always scopes by `SearchScope.user_id` + the conversation's indexed `document_ids`.

## Invariants

1. Schema changes go through Alembic migrations only; app startup fails if `alembic_version` is missing.
2. Core classes take dependencies via constructor; only `core/factory.py` reads `app.config.settings`.
3. Every retrieval query filters by `user_id`; a user never sees another user's chunks.
4. Re-ingest replaces a document's chunks in one transaction (delete + insert); skipped when hash unchanged unless `force`.
5. `embedding_dim` must match `vector(768)`; changing it needs a new migration + full re-ingest.
6. Answers must cite `[n]` sources; no valid citation → `grounded=False`. No relevant chunks → refusal without calling the LLM.
7. Blocking work (PyMuPDF) runs via asyncio.to_thread.
8. API `SearchScope.document_ids` is never empty (empty = all of the user's documents); chat returns 409 instead.
9. Ingestion goes through the Postgres queue: workers claim with `FOR UPDATE SKIP LOCKED`, stale `processing` jobs are reclaimed, attempts are capped, shutdown releases jobs back to `pending`.
10. Upload endpoint never declares `UploadFile`: auth, Content-Length, upload slot, free disk and quota checks run before the body is parsed.
11. Chat concurrency is limited per process (semaphore + one stream per user); the stream holds no DB connection.
12. LLM streaming uses AsyncOpenAI (no thread per request); the stream is closed, cancelling the upstream request, when the client disconnects.
