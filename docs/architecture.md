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
| LLM          | Gemini `gemini-3.5-flash-lite` (`google-genai`) | Answer generation, stream / non-stream                   |
| Embedding    | Gemini `gemini-embedding-2` (768-d)            | Chunk and query vectors                                  |
| Reranker     | Laya MLX (Apple Silicon) / `NoOpReranker`      | Relevance rerank of fused candidates                     |
| Parsing      | PyMuPDF + HF `tokenizers` (ModernBERT)         | PDF → blocks → token-bounded chunks                      |

## System Boundaries

- `client/src/api` — HTTP layer: `apiFetch`, endpoint URLs (`config.ts`), services, response types.
- `client/src/pages`, `components`, `store` — views, shadcn UI, Zustand auth state; no direct `fetch`.
- `server/app/routers` — HTTP endpoints (auth, document, conversation, heartbeat); thin, delegate to cruds/core.
- `server/app/cruds` — ORM CRUD for request-scoped `AsyncSession` (users, documents).
- `server/app/models`, `alembic/` — ORM models and the migrations that define the real schema.
- `server/app/core` — RAG engine, framework-agnostic: ingestion, embedding, storage repos, retrieval, rerank, generation, LLM. Depends only on `interfaces.py` Protocols.
- `server/app/core/factory.py` — composition root; the only core file that reads `settings`.
- `server/scripts` — `rag_cli.py` (ingest/search/ask/eval), `seed.py`, run script.
- `server/tests/core` — unit tests for pure core logic (no DB/API).

## Storage Model

- **PostgreSQL**: `users`; `documents` (owner, name, status `pending|processing|indexed|failed`, `content_hash`, counts, error); `document_chunks` (content, section, pages, `overlap_chars`, `vector(768)` embedding, denormalized `user_id`) with HNSW and BM25 indexes.
- **Local disk (`DOCUMENTS_FOLDER`)**: uploaded original files, flat folder keyed by filename.
- **Browser localStorage**: `access_token`, `token_type`, `isLoggedIn`.

## Auth and Access Model

- Users register/login via `/api/auth`; login returns a JWT (`sub` = username), sent as `Bearer` header.
- Every document and chunk has a single owner (`user_id`); no sharing/collaborators.
- Document list/upload/delete require auth and filter by `current_user.id`; retrieval always scopes by `SearchScope.user_id` (+ optional `document_ids`).
- Gaps: `GET /document/{filename}` and `POST /conversation/stream` are currently unauthenticated.

## Invariants

1. Schema changes go through Alembic migrations only; app startup fails if `alembic_version` is missing.
2. Core classes take dependencies via constructor; only `core/factory.py` reads `app.config.settings`.
3. Every retrieval query filters by `user_id`; a user never sees another user's chunks.
4. Re-ingest replaces a document's chunks in one transaction (delete + insert); skipped when hash unchanged unless `force`.
5. `embedding_dim` must match `vector(768)`; changing it needs a new migration + full re-ingest.
6. Answers must cite `[n]` sources; no valid citation → `grounded=False`. No relevant chunks → refusal without calling the LLM.
7. Blocking work (PyMuPDF, Laya) runs via `asyncio.to_thread`; Laya guarded by a lock.
