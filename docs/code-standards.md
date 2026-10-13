# Code Standards

## General

- One file, one responsibility (loader, chunker, retriever, reranker…); keep routers thin.
- Depend on Protocols in `core/interfaces.py`, wire concrete classes in `core/factory.py`.
- Fix root causes; do not swallow exceptions (surface LLM `error` events, wrap in `RAGError` subclasses).
- Do not mix HTTP concerns (SSE, `HTTPException`) into `core` beyond the existing LLM stream.

## Python

- Python 3.11+, full type hints, `X | None` style.
- Format/lint: `make format` / `make quality` (black, isort, flake8, max line 79).
- Domain objects are `@dataclass(frozen=True, slots=True)` in `core/domain.py`, no ORM/SDK imports.
- Async everywhere for I/O; sync CPU-bound work via `asyncio.to_thread`.
- Config only through `app.config.Settings` (`.env`); add new keys to `.env.example` too.
- Logging via `loguru`; tests via `pytest` + `pytest-asyncio` (`make test`), fakes over real DB/API.

## TypeScript / React

- Use `@/` path alias; function components + hooks.
- All HTTP through `apiFetch` and a service in `api/services`; URLs only in `api/config.ts`, types in `api/types`.
- Global state in Zustand stores (`store/`); local UI state with `useState`.
- `strict` is off today — still avoid `any`, type API responses explicitly.

## Styling

- Tailwind utilities with shadcn theme tokens (`bg-background`, `text-muted-foreground`…); no hardcoded hex.
- Reuse `components/ui` primitives; merge classes with `cn()` from `lib/utils`.
- Radius from `--radius`; dark mode via `.dark` CSS variables in `global/globals.css`.

## API Routes

- Mounted under `/api/<resource>`; one router package per resource (`routers/<name>/endpoint.py`).
- Validate input with Pydantic schemas (`app/schemas`) before logic.
- Require `Depends(get_current_user)` and filter by owner on every user-data route.
- Errors via `HTTPException` with clear `detail`; list responses wrapped (`{"documents": [...]}`).
- Streaming responses use `sse-starlette` `EventSourceResponse`; SSE `data` is always JSON (even tokens).
- Streaming routes do not depend on `get_db`; they use short sessions (`AsyncSessionLocal`) so no connection is held while streaming.
- Never declare `UploadFile` / `File` params on upload routes; take `Request` and call `request.form()` after the checks.

## Data and Storage

- Metadata and chunks (text + vectors) live in Postgres; original files on disk under `DOCUMENTS_FOLDER`.
- Repositories/retrievers receive `async_sessionmaker` and open their own session per operation.
- Raw SQL only via `text()` with bind params (never string-concat user input); `SET LOCAL` values cast to `int` first.
- ORM-unrepresentable objects (BM25 index, extensions) go in migrations via `op.execute`.

## File Organization

- `client/src/api/` — API client, endpoint config, services, types.
- `client/src/pages/`, `components/`, `store/`, `hooks/` — views, UI, global state, hooks.
- `server/app/routers/`, `schemas/`, `cruds/`, `models/` — HTTP layer, DTOs, CRUD, ORM.
- `server/app/core/` — RAG engine (`ingestion/`, `embedding/`, `storage/`, `retrieval/`, `rerank/`, `generation/`, `llm/`, `prompt/`).
- `server/alembic/versions/` — numbered migrations (`000N_<name>.py`).
- `server/scripts/`, `server/tests/core/`, `server/eval/` — CLI tools, unit tests, golden sets.
- `docs/` — context files and specs (`docs/specs/`).
