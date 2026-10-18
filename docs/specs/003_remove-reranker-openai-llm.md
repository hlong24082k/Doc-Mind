# Spec 003 — Bỏ bước rerank, chuyển LLM sang OpenAI SDK

## 1. Goal

Xóa toàn bộ bước rerank (Laya và `NoOpReranker`) khỏi RAG core. Thay `GeminiProvider` bằng `OpenAIProvider`, dùng `AsyncOpenAI` gọi Chat Completions, để cùng một code chạy được với Gemini (endpoint OpenAI-compat), vLLM serve, OpenRouter… chỉ bằng cách đổi `.env`. Hành vi của API giữ nguyên: thứ tự RRF, ngưỡng dense, số chunk đưa vào context, SSE stream.

## 2. Design

### 2.1 Quyết định đã chốt

| # | Chủ đề | Quyết định | Lý do |
|---|---|---|---|
| 1 | Phạm vi bỏ rerank | Xóa hẳn: `core/rerank/`, `Reranker` Protocol, `RerankerUnavailableError`, tham số `reranker`/`min_score` của `RAGService`, `search(rerank=...)`, settings `reranker`/`laya_*`/`api_reranker`/`rerank_min_score`, cờ CLI `--rerank`/`--reranker`, mode eval `hybrid+rerank`. Đổi `rerank_top_n` thành `retrieval_top_n` (mặc định 5) | Laya chưa đạt chất lượng. Không có Laya thì `NoOpReranker` chỉ còn làm `[:top_n]`, Protocol chỉ có một implementation pass-through. Cần reranker thật sau này thì thêm lại khoảng 5 dòng trong `RAGService` |
| 2 | Dependency và file phụ | Xóa `laya-mlx` và `server/notebook/systemOne_laya.py`. **Giữ** tokenizer ModernBERT của chunker | Đổi tokenizer thì chunk thay đổi và phải re-ingest toàn bộ |
| 3 | Tài liệu | Sửa `architecture.md`, `code-standards.md`, `progress-tracker.md`. Hai spec cũ (`rag-core.md`, `document-conversation-api.md`) giữ nguyên làm lịch sử | — |
| 4 | API OpenAI | Chat Completions (`client.chat.completions.create`) với `AsyncOpenAI` | Được hỗ trợ rộng nhất (vLLM, Gemini, Ollama, OpenRouter, LiteLLM). Responses API hỗ trợ không đồng đều |
| 5 | Backend mặc định | Gemini qua `https://generativelanguage.googleapis.com/v1beta/openai/`, model `gemini-3.5-flash-lite` | Hành vi như cũ, không cần tài khoản mới |
| 6 | Settings LLM | `llm_base_url`, `llm_api_key`, `llm_model`, `llm_reasoning_effort` (rỗng thì không gửi). Xóa `gemini_model`, `gemini_thinking_level`. **Giữ** `gemini_api_key` cho embedding | Tên chung, không gắn với nhà cung cấp. Không thêm timeout/retries/temperature, dùng mặc định SDK |
| 7 | Cấu trúc provider | `core/llm/openai_provider.py` → `OpenAIProvider(LLMBase)`, xóa `gemini_provider.py`. **Giữ nguyên contract** `LLMBase` (stream thì yield `ServerSentEvent` message/error, non-stream trả `LLMResponse`). Constructor nhận `client`/`model` tường minh, không đọc `settings`. Factory có thêm `build_llm()` public | `AnswerGenerator`, `QueryRewriter`, router không phải sửa. Sửa luôn chỗ vi phạm invariant #2 (`GeminiProvider` tự đọc `settings`) |
| 8 | Safety settings | Bỏ | OpenAI-compat không có tham số này. Model Gemini hiện tại mặc định đã không chặn |
| 9 | Embedding và dependency | `GeminiEmbedder` (`google-genai`) giữ nguyên. Xóa `google-generativeai` (không dùng). Thêm `openai` | Đổi embedding thì phải re-ingest (vector 768 chiều) |
| 10 | Test và tên spec | Thêm `tests/core/test_openai_provider.py` (fake client + type thật của SDK), sửa `test_rag_service.py`. Spec ở file này | — |
| 11 | `retrieval_candidates` | **Giữ**. `RAGService` vẫn retrieve `max(candidates, k)`, xét ngưỡng dense trên toàn bộ candidate, rồi cắt `[:k or top_n]` | Nếu retrieve thẳng `top_n`, chunk #1 của nhánh dense có thể bị RRF đẩy khỏi top 5, ngưỡng dense từ chối nhiều hơn mà chưa có eval để đo |

### 2.2 Luồng truy vấn sau thay đổi

```
query
  └─► HybridRetriever (dense ‖ sparse → RRF, k = max(retrieval_candidates, k))
        └─► gate: max(dense) < retrieval_min_dense_score → refusal (không gọi LLM)
              └─► cắt [:k or retrieval_top_n]
                    └─► ContextBuilder (small-to-big)
                          └─► AnswerGenerator ─► OpenAIProvider.generate(stream=True|False)
                                                   └─► AsyncOpenAI.chat.completions.create
                                                         (LLM_BASE_URL: Gemini | vLLM | …)
```

So với hiện tại, API chỉ khác ở chỗ không còn khóa `timings_ms["rerank"]`. Thời gian của `NoOpReranker` gần như bằng 0, và client không đọc khóa này. Chunk vẫn mang `scores` `dense`/`sparse`/`rrf`, không còn `rerank`.

### 2.3 Ánh xạ tham số Gemini SDK → OpenAI SDK

| Cũ (`google-genai`) | Mới (`openai`) |
|---|---|
| `client.aio.models.generate_content_stream` | `await client.chat.completions.create(..., stream=True)` → `AsyncStream` |
| `client.aio.models.generate_content` | `await client.chat.completions.create(...)` → `ChatCompletion` |
| `system_instruction=` | message `{"role": "system", ...}` đứng đầu (bỏ qua nếu `None`/rỗng) |
| `contents=[Content(role="user", ...)]` | message `{"role": "user", "content": query}` |
| `ThinkingConfig(thinking_level="minimal")` | `reasoning_effort="minimal"` (chỉ gửi khi setting không rỗng) |
| `safety_settings`, `automatic_function_calling=disable` | Bỏ (không có tool nào được truyền nên không có function calling) |
| `chunk.text` | `chunk.choices[0].delta.content` (bỏ qua chunk có `choices` rỗng hoặc `content` `None`) |
| `resp.text` | `resp.choices[0].message.content` |
| `resp.candidates[0].finish_reason` | `resp.choices[0].finish_reason` |
| `resp.usage_metadata.model_dump()` | `resp.usage.model_dump()` |

Ghi chú vLLM: khi bật reasoning parser, phần suy nghĩ nằm ở `delta.reasoning_content`, nên bị bỏ qua (không trả cho user). Đó đúng là hành vi mong muốn.

## 3. Implementation

### 3.1 Xóa file

- `server/app/core/rerank/` (cả thư mục: `__init__.py`, `laya_reranker.py`, `noop_reranker.py`)
- `server/app/core/llm/gemini_provider.py`
- `server/notebook/systemOne_laya.py` (xóa thư mục `notebook/` nếu rỗng)

### 3.2 `server/app/core/llm/openai_provider.py` (mới)

```python
from typing import Any, AsyncIterator

from openai import AsyncOpenAI
from sse_starlette.event import ServerSentEvent

from app.core.errors import LLMGenerationError
from app.core.llm.base import LLMBase, LLMResponse


class OpenAIProvider(LLMBase):
    """Chat Completions qua OpenAI SDK: chạy với mọi endpoint tương thích
    OpenAI (OpenAI, Gemini OpenAI-compat, vLLM serve, OpenRouter...)."""

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        *,
        reasoning_effort: str | None = None,
    ):
        super().__init__(provider_name="openai")
        self.client = client
        self.model = model
        self.reasoning_effort = reasoning_effort

    def _request(
        self, query: str, system_instruction: str | None
    ) -> dict[str, Any]:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": query})
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        # nhiều model trên vLLM không nhận tham số này → chỉ gửi khi có cấu hình
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        return kwargs

    async def _generate_stream(
        self, query: str, system_instruction: str | None
    ) -> AsyncIterator[ServerSentEvent]:
        try:
            stream = await self.client.chat.completions.create(
                **self._request(query, system_instruction), stream=True
            )
            # async with: client ngắt kết nối → CancelledError → đóng HTTP
            # response, upstream ngừng sinh token (không tốn thêm quota)
            async with stream:
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield ServerSentEvent(
                            data=chunk.choices[0].delta.content, event="message"
                        )
        except Exception as e:  # CancelledError là BaseException → propagate
            yield ServerSentEvent(
                data=f"[Error] LLM streaming failed: {e}", event="error"
            )

    async def _generate_once(
        self, query: str, system_instruction: str | None
    ) -> LLMResponse:
        try:
            resp = await self.client.chat.completions.create(
                **self._request(query, system_instruction)
            )
        except Exception as e:
            raise LLMGenerationError(f"LLM generation failed: {e}") from e
        choice = resp.choices[0] if resp.choices else None
        return LLMResponse(
            text=choice.message.content if choice else None,
            provider=self.provider,
            metadata={
                "model": self.model,
                "finish_reason": choice.finish_reason if choice else None,
                "usage": resp.usage.model_dump() if resp.usage else None,
            },
        )
```

- Không có khối `__main__` (để chạy được thì nó sẽ phải đọc `settings`). Smoke test làm theo §5.
- `core/llm/base.py` và `core/llm/post_processor.py` giữ nguyên.

### 3.3 `server/app/config.py`

- Mục `# ---- Gemini setting ----`: chỉ giữ `gemini_api_key`, comment đổi thành `# ---- Gemini (embedding) ----`. Xóa `gemini_model`, `gemini_thinking_level`.
- Thêm mục mới ngay sau:

```python
# ---- LLM (endpoint tương thích OpenAI: Gemini, vLLM, OpenRouter...) ----
llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
llm_api_key: str = ""
llm_model: str = "gemini-3.5-flash-lite"
llm_reasoning_effort: str = "minimal"  # rỗng = không gửi (vd. vLLM)
```

- `# ---- Retrieval ----`: sửa comment `retrieval_candidates` thành `# số candidate xét ngưỡng dense trước khi cắt top_n`. Thêm `retrieval_top_n: int = 5  # số chunk đưa vào context`.
- Xóa cả mục `# ---- Rerank ----` (`reranker`, `laya_model`, `laya_dtype`, `rerank_top_n`, `rerank_min_score`).
- Mục `# ---- Chat ----`: xóa `api_reranker`.

### 3.4 `server/.env.example`

- Mục Gemini: chỉ giữ `GEMINI_API_KEY`, tiêu đề đổi thành `Google Gemini API (embedding)`.
- Thêm mục:

```
# ==========================================
# LLM (OpenAI-compatible Chat Completions)
# ==========================================
# Gemini: https://generativelanguage.googleapis.com/v1beta/openai/
# vLLM:   http://localhost:8001/v1  (LLM_API_KEY tùy ý nếu không bật --api-key, vd. "EMPTY")
LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
LLM_API_KEY="your-gemini-api-key-here"
LLM_MODEL="gemini-3.5-flash-lite"
# minimal | low | medium | high; để rỗng nếu model không hỗ trợ
LLM_REASONING_EFFORT="minimal"
```

- RAG Core: xóa các dòng `RERANKER`, `LAYA_MODEL`, `LAYA_DTYPE`, `RERANK_MIN_SCORE` và comment `# laya | none…`. Đổi `RERANK_TOP_N=5` thành `RETRIEVAL_TOP_N=5`, đặt sau `RETRIEVAL_CANDIDATES`. Sửa comment của `RETRIEVAL_CANDIDATES` cho khớp §3.3.
- Chat: xóa `API_RERANKER` và comment phía trên nó.

> Migration `.env` của dev: đổi `RERANK_TOP_N` thành `RETRIEVAL_TOP_N`, thêm 4 key `LLM_*` (`LLM_API_KEY` = giá trị `GEMINI_API_KEY`). Key cũ còn sót lại thì bị bỏ qua (`extra="ignore"`), nên không lỗi khi khởi động.

### 3.5 `server/app/core/factory.py`

- Import: bỏ `GeminiProvider`, `LayaReranker`, `NoOpReranker`, `Reranker`. Thêm `from openai import AsyncOpenAI` và `from app.core.llm.openai_provider import OpenAIProvider`.
- Xóa `_laya`, `_llm`, `build_reranker`.
- Thêm:

```python
@lru_cache(maxsize=None)
def _openai_client(base_url: str, api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def build_llm(s: Settings = settings) -> OpenAIProvider:
    return OpenAIProvider(
        _openai_client(s.llm_base_url, s.llm_api_key),
        s.llm_model,
        reasoning_effort=s.llm_reasoning_effort or None,
    )
```

- `build_rag_service(*, mode="hybrid", s=settings, query_max_retries=None)`: bỏ tham số `reranker`. Khi gọi `RAGService`, bỏ `reranker=` và `min_score=`, dùng `generator=AnswerGenerator(build_llm(s))`, `top_n=s.retrieval_top_n`, giữ `candidates=s.retrieval_candidates`.
- `build_query_rewriter`: `QueryRewriter(build_llm(s), timeout_s=...)`.
- `build_api_services`: bỏ `reranker=s.api_reranker`.
- `_genai_client` và `build_embedder` giữ nguyên.

### 3.6 `server/app/core/rag_service.py`

- Docstring: `"""Orchestrator truy vấn: retrieve → context → generate."""`.
- Bỏ import `Reranker`.
- `__init__(self, retriever, context_builder, generator, candidates=30, top_n=5, min_dense_score=None)`: bỏ `reranker` và `min_score`.
- `search(self, query, scope, *, k=None)`: bỏ tham số `rerank`. Sau bước gate dense, thay toàn bộ khối `if rerank and found: … else: …` bằng `chunks = found[: k or self.top_n]`. Sửa comment gate: "… thì bỏ qua LLM".
- `_prepare`, `answer`, `answer_stream`, `_refusal`, `_finalize` giữ nguyên.

### 3.7 Phần còn lại của core

- `core/interfaces.py`: xóa `class Reranker(Protocol)`.
- `core/errors.py`: xóa `RerankerUnavailableError`.
- `core/domain.py:86`: sửa comment thành `# {"dense": .., "sparse": .., "rrf": ..}`.
- `core/ingestion/chunker.py:40`: sửa docstring thành `"…, đo bằng token của ModernBERT."`.
- `core/ingestion/tokenizer.py:5`: sửa docstring thành `"Đếm token theo tokenizer HuggingFace (ModernBERT)."`.

### 3.8 `server/scripts/rag_cli.py`

- Bỏ `from app.core.llm.gemini_provider import GeminiProvider`.
- `EVAL_MODES = ("dense", "sparse", "hybrid")`.
- `cmd_search`: `service.search(args.query, scope, k=args.k)`.
- `cmd_ask`: `factory.build_rag_service()`.
- `cmd_eval_gen`: `llm = factory.build_llm()`.
- `cmd_eval`: bỏ dòng `base, rerank = …` và dòng `service.min_score = None`. Dùng `factory.build_rag_service(mode=mode)` và `service.search(item["question"], scope, k=max(ks))`.
- Parser: bỏ `--rerank` của `search` và `--reranker` của `ask`.

### 3.9 Tests

**`tests/core/test_rag_service.py`**: xóa `FakeReranker`. `svc()` thành `RAGService(FakeRetriever(chunks), None, None, min_dense_score=min_dense)`. Assert đầu tiên còn `a.refused and "llm" not in a.timings_ms`.

**`tests/core/test_openai_provider.py`** (mới). Fake client có `chat.completions.create(**kwargs)` lưu lại `kwargs`, rồi trả về kết quả dựng sẵn hoặc raise. Kết quả dựng bằng **type thật** của SDK (`ChatCompletion.model_validate({...})`, `ChatCompletionChunk.model_validate({...})`) để bắt sai tên thuộc tính. Fake stream là class có `__aenter__`/`__aexit__`/`__aiter__`. Các case:

1. Stream: các chunk `"Hel"`, chunk `choices=[]`, chunk `content=None`, `"lo"` → yield đúng 2 event `message` (`"Hel"`, `"lo"`). `kwargs["stream"] is True`. `messages` = `[system, user]`.
2. Stream: `create` raise `RuntimeError("boom")` → đúng 1 event `error`, `data` bắt đầu bằng `"[Error]"` và chứa `"boom"`.
3. Non-stream: trả `LLMResponse(text="hi", provider="openai")`, `metadata` có `model`, `finish_reason == "stop"`, `usage["total_tokens"]`.
4. Non-stream: `create` raise → `LLMGenerationError`.
5. `reasoning_effort=None` thì khóa `reasoning_effort` không có trong `kwargs`. `reasoning_effort="minimal"` thì có.
6. `system_instruction=None` → `messages` chỉ có 1 message `user`.

`tests/core/test_context_builder.py`: đổi tên `test_order_follows_rerank_and_refs_numbered` thành `test_order_follows_input_and_refs_numbered`. Nội dung test giữ nguyên.

`test_query_rewriter.py` (import `LLMResponse` từ `base`) giữ nguyên.

### 3.10 Tài liệu

**`docs/architecture.md`**
- Bảng Stack: dòng LLM thành `| LLM | Any OpenAI-compatible Chat Completions endpoint (`openai` SDK, `AsyncOpenAI`); default Gemini `gemini-3.5-flash-lite` via OpenAI-compat | Answer generation + query rewrite, stream / non-stream |`. Xóa dòng Reranker.
- System Boundaries, `server/app/core`: bỏ `rerank` khỏi danh sách.
- Invariant 7: `Blocking work (PyMuPDF) runs via asyncio.to_thread.`
- Invariant 12: `LLM streaming uses AsyncOpenAI (no thread per request); the stream is closed, cancelling the upstream request, when the client disconnects.`

**`docs/code-standards.md`**
- `(loader, chunker, retriever, reranker…)` thành `(loader, chunker, retriever…)`.
- File Organization: bỏ `rerank/` khỏi danh sách thư mục core.

**`docs/progress-tracker.md`**
- Current Goal: branch `feat/update-chat-core`, implement spec này.
- Completed: thêm mục (ngày) bỏ rerank stage và chuyển LLM sang OpenAI SDK.
- Next Up: `Run eval baseline and tune retrieval_min_dense_score`.
- Open Questions: thay dòng Laya trên Linux bằng `Reranker removed (2026-10-18); revisit (cross-encoder) after eval baseline`.
- Architecture Decisions: dòng ModernBERT thêm `(Laya removed; kept to avoid re-ingest)`. Dòng `api_reranker=none` thay bằng quyết định mới: bỏ rerank, LLM qua Chat Completions tương thích OpenAI.
- Session Notes: xóa `Non-Mac: set RERANKER=none.`, giữ phần về port.

## 4. Dependencies

```bash
cd server
uv remove laya-mlx google-generativeai
uv add "openai>=3.35"
```

- `uv.lock` được cập nhật, không còn `laya-mlx`, `mlx*` và `google-generativeai` (cùng các dep chỉ phục vụ chúng).
- `google-genai` giữ lại (embedding). `sse-starlette` giữ lại (contract `LLMBase` + router).
- CI (`uv sync --locked`) phải pass với lockfile mới.

## 5. Verification checklist

**Code sạch**
- [ ] `grep -rniE 'laya|rerank|GeminiProvider|gemini_model|thinking_level|api_reranker' server/app server/scripts server/tests server/.env.example server/pyproject.toml` không còn kết quả nào.
- [ ] `grep -rn 'from app.config' server/app/core` chỉ còn trong `factory.py`.

**Tests**
- [ ] `cd server && uv run pytest` pass toàn bộ, kể cả `test_openai_provider.py` mới.
- [ ] CI (`.github/workflows/ci.yml`) xanh trên PR.

**LLM qua Gemini OpenAI-compat**
- [ ] `uv run python -c "import asyncio; from app.core import factory; print(asyncio.run(factory.build_llm().generate('say hi', stream=False)))"` trả `LLMResponse` có `text`, `finish_reason`, `usage`.
- [ ] `uv run python scripts/rag_cli.py ask "…" --show-context`: stream ra token, có Sources `[n]`, `grounded=True`. Trong timings không còn `rerank`.
- [ ] `ask … --no-stream` cho kết quả tương đương.
- [ ] Câu hỏi ngoài tài liệu thì refusal, không gọi LLM (timings không có `llm`).
- [ ] `LLM_API_KEY` sai → API chat trả SSE `error` với detail `LLM streaming failed: …`. Server không crash.

**API / UI**
- [ ] Chat trên UI: stream bình thường. Follow-up được rewrite (log không có `Query rewrite failed`). Bấm Stop giữa chừng thì server log không có lỗi và request upstream bị hủy.
- [ ] `messages.timings_ms` của tin nhắn mới không còn khóa `rerank`.

**CLI**
- [ ] `rag_cli.py search "…" -k 10` chạy được. Cột điểm chỉ có `dense`/`sparse`/`rrf`.
- [ ] `rag_cli.py eval eval/golden.sample.jsonl` in bảng cho 3 mode `dense`/`sparse`/`hybrid`.
- [ ] `rag_cli.py eval-gen --doc <id> --n 2` sinh được câu hỏi qua `build_llm()`.

**Tương thích provider khác (tùy chọn, nếu có sẵn)**
- [ ] Trỏ `LLM_BASE_URL` sang một server vLLM (`vllm serve <model>`), `LLM_REASONING_EFFORT=""`: `ask` chạy được, không đổi code.

**Docs**
- [ ] `architecture.md`, `code-standards.md`, `progress-tracker.md` đã cập nhật theo §3.10.
