# Progress Tracker

Update this file after every meaningful implementation
change.

## Current Phase

- In progress — RAG core wired into the API and UI (document + conversation API implemented); manual verification and load check pending.

## Current Goal

- Branch `feat/update-chat-core`: implement `docs/specs/003_remove-reranker-openai-llm.md`.

## Completed

- Auth: register/login (JWT + Argon2), protected client routes, Zustand auth store.
- Documents: upload (multi-file), list, download, delete endpoints + Documents page.
- Conversation: plain-LLM `/conversation/stream` (replaced on 2026-10-13 by the RAG conversation API below).
- Postgres migration (from earlier store), ParadeDB image, Alembic (`0001_baseline`, `0002_rag_core`).
- RAG core (`server/app/core`): PDF loader, structured chunker, Gemini embedder, pgvector + BM25 hybrid retrieval with RRF, small-to-big context, cited answers, stream/non-stream LLM.
- `scripts/rag_cli.py` (ingest/docs/chunks/search/ask/eval-gen/eval) and unit tests in `tests/core`.
- (2026-10-13) Spec `document-conversation-api.md` implemented:
  - Migration `0003_conversations`: queue columns, `size_bytes`, unique `(user_id, lower(name))`, `conversations`, `messages`.
  - Upload: `Request`-based multipart endpoint with auth / Content-Length / slot / free-disk / quota checks before parsing, chunked copy + sha256, per-user files `{uid}/{name}.pdf`, `canonical_document_name`.
  - Postgres-queue `IngestionWorker` (lifespan task or `scripts/ingest_worker.py`), `pipeline.run()` split from CLI `ingest()`.
  - Document API: list + usage, file (inline PDF), reindex, delete (removes file). Old `/conversation/stream` removed.
  - Conversation API: CRUD + SSE `POST /{id}/messages` (meta → contexts → token → final / error), `QueryRewriter` for follow-ups, `ChatLimiter`, history persisted.
  - Gemini streaming via async SDK; `get_current_user` uses its own short session; DB pool from settings.
  - Tests: ingest worker, query rewriter, naming, auth-required, upload route/helpers. `scripts/load_chat.py`.
  - Client: Documents page (status badges, polling, usage, multi-select chat, open PDF), Chat page (conversation list, new chat dialog, streaming with citations/sources, stop/retry), `apiStream`, 401 → login.
- (2026-10-18) Spec `003_remove-reranker-openai-llm.md` implemented: rerank stage removed (`core/rerank/`, `Reranker`, settings, CLI flags, `hybrid+rerank` eval mode); `retrieval_top_n` replaces `rerank_top_n`; `GeminiProvider` → `OpenAIProvider` + `factory.build_llm()`; deps `laya-mlx`/`google-generativeai` out, `openai` in; new `tests/core/test_openai_provider.py`. Live LLM/UI checks of spec §5 pending.
- (2026-10-13) CI: `.github/workflows/ci.yml` on PRs and pushes to `develop`/`main` — server `uv sync --locked` + `pytest`; client `npm ci`, lint, `tsc --noEmit`, build. No DB/Gemini needed (tests use fakes). `make quality` not in CI (see Open Questions).

- (2026-10-19) Docker Compose full stack: `server/Dockerfile` (uv, migrations on start), `nginx/Dockerfile` + `nginx/nginx.conf` (SPA + `/api` proxy, SSE unbuffered, 100 MB body), postgres healthcheck, `./server/documents` bind-mounted, HF tokenizer cache volume. Verified: build, migrations, login and document list via nginx; SSE chat through nginx not yet exercised.

## In Progress

- Verification checklist (§5 of the spec): manual UI checks, upload limits (503/507/quota), kill/restart ingest, load check (`load_chat.py`) and recording TTFT p50/p95 in the spec.

## Next Up

- Run eval baseline and tune `retrieval_min_dense_score`.

## Open Questions

- Vietnamese queries on English docs (BM25 weak): fold translation into `QueryRewriter` later?
- Reranker removed (2026-10-18); revisit (cross-encoder) after eval baseline.
- AGPL (PyMuPDF, ParadeDB) acceptable beyond demo?
- `make quality` cannot pass as configured: black/isort/flake8 are not in dev deps, and flake8 uses max line 79 while black formats at 88 (existing code already exceeds 79).

## Architecture Decisions

- Postgres for everything (pgvector + ParadeDB BM25): one store, user filter push-down, no extra service.
- Fusion (RRF) in Python, not SQL: branches testable separately, reusable for CLI `--mode`.
- `user_id` denormalized on `document_chunks` so HNSW/BM25 filter without joins.
- Chunk tokens counted with ModernBERT tokenizer so passages fit Laya's context unchanged (Laya removed; kept to avoid re-ingest).
- Alembic owns schema; `create_all` removed to keep migrations the single source of truth.
- Mandatory citations + refusal before LLM when retrieval is weak, to limit hallucination.
- Composition root in `core/factory.py`; core is framework-agnostic and unit-testable.
- (2026-10-13) Ingestion via Postgres queue (`documents.status` + `FOR UPDATE SKIP LOCKED`), in-process by default, separate worker process to scale; no Redis.
- (2026-10-13) Conversations persisted (`conversations`, `messages`), scoped to 1..10 indexed documents, follow-ups rewritten to standalone questions.
- (2026-10-18) Rerank stage removed (Laya/NoOp); LLM goes through OpenAI-compatible Chat Completions (`AsyncOpenAI`, `llm_*` settings) so Gemini/vLLM/OpenRouter swap via `.env`. Embedding stays on Gemini.
- (2026-10-13) Files stored at `{user_id}/{name}.pdf` with `name` canonicalized (NFC, forbidden chars → `_`, ≤ 200 bytes) and unique on `(user_id, lower(name))` (APFS is case/normalization-insensitive).
- (2026-10-13) Upload stays multipart, but the endpoint takes `Request` and parses the form only after auth, Content-Length, per-process semaphore, free-disk and per-user quota checks (FastAPI parses declared `UploadFile` params before auth). Benchmark: upload costs ~1-2.4 CPU-s/GB; risk is disk, not CPU.

## Session Notes

- Full stack: `docker compose up -d --build` → http://localhost (`NGINX_PORT` to change). Uses `server/.env`; compose overrides `POSTGRES_HOST/PORT`, `DOCUMENTS_FOLDER`, `TMPDIR`, `DEBUG=false`. Postgres credentials come only from `server/.env`.
- Dev: `docker compose up -d postgres` → `cd server && uv run alembic upgrade head` → `uv run python server.py`; client `npm run dev` (`VITE_API_BASE_URL=http://localhost:8000/api`).
- DB host port defaults to 5433 in compose; match `POSTGRES_PORT` in `server/.env`.
- Specs: `docs/specs/rag-core.md`, `docs/specs/document-conversation-api.md`; CLI usage: `docs/usaged/manual_usage_rag_cli.md` (gitignored).
- Set `TMPDIR` to a folder on the documents volume before starting the API (`mkdir -p documents/.upload-tmp && export TMPDIR=$PWD/documents/.upload-tmp`).
- 2026-10-13 smoke test: Gemini latency was very high (non-stream "say hi" took ~170 s), so the 8 s rewrite timeout fell back to the original question; TTFT numbers from that day are not representative.
