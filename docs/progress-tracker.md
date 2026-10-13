# Progress Tracker

Update this file after every meaningful implementation
change.

## Current Phase

- In progress — RAG core done; integrating it into the API and UI.

## Current Goal

- Branch `feat/build-document-endpoints`: wire RAG core into document endpoints (ingest on upload, status, chunks) and then into conversation.

## Completed

- Auth: register/login (JWT + Argon2), protected client routes, Zustand auth store.
- Documents: upload (multi-file), list, download, delete endpoints + Documents page.
- Conversation: `/conversation/stream` SSE endpoint streaming Gemini output (plain LLM, no RAG).
- Postgres migration (from earlier store), ParadeDB image, Alembic (`0001_baseline`, `0002_rag_core`).
- RAG core (`server/app/core`): PDF loader, structured chunker, Gemini embedder, pgvector + BM25 hybrid retrieval with RRF, Laya/NoOp rerank, small-to-big context, cited answers, stream/non-stream LLM.
- `scripts/rag_cli.py` (ingest/docs/chunks/search/ask/eval-gen/eval) and unit tests in `tests/core`.

## In Progress

- Document endpoints using `IngestionPipeline` / `DocumentStore`.

## Next Up

- Trigger ingestion after upload (background task) and expose `status` / `num_chunks` / `error` in UI.
- RAG chat endpoint using `RAGService.answer_stream` (contexts → tokens → final with citations), scoped by user + optional document.
- Wire `ChatPage` to the real endpoint (currently mocked with `setTimeout`), show sources.
- Secure `GET /document/{filename}` and `/conversation/stream` with auth + ownership.
- Delete file from disk on document delete; store files per user to avoid name collisions.
- Run eval baseline and tune `rerank_min_score` / `retrieval_min_dense_score`.

## Open Questions

- Ingestion on upload: FastAPI `BackgroundTasks` vs a worker queue?
- Name key mismatch: cruds use `filename.split(".")[0]`, pipeline uses `path.stem` — unify.
- Multi-turn chat / question rewriting and Vietnamese queries on English docs (BM25 weak) — later phase?
- Reranker on Linux/Docker deploy (Laya is Apple-Silicon only) — `none` or a cross-encoder?
- AGPL (PyMuPDF, ParadeDB) acceptable beyond demo?

## Architecture Decisions

- Postgres for everything (pgvector + ParadeDB BM25): one store, user filter push-down, no extra service.
- Fusion (RRF) in Python, not SQL: branches testable separately, reusable for CLI `--mode`.
- `user_id` denormalized on `document_chunks` so HNSW/BM25 filter without joins.
- Chunk tokens counted with ModernBERT tokenizer so passages fit Laya's context unchanged.
- Alembic owns schema; `create_all` removed to keep migrations the single source of truth.
- Mandatory citations + refusal before LLM when retrieval is weak, to limit hallucination.
- Composition root in `core/factory.py`; core is framework-agnostic and unit-testable.

## Session Notes

- Run: `docker compose up -d` → `cd server && uv run alembic upgrade head` → `uv run python server.py`; client `npm run dev` (`VITE_API_BASE_URL=http://localhost:8000/api`).
- Non-Mac: set `RERANKER=none`. DB host port defaults to 5433 in compose; match `POSTGRES_PORT` in `server/.env`.
- Specs: `docs/specs/rag-core.md`; CLI usage: `docs/usaged/manual_usage_rag_cli.md` (gitignored).
