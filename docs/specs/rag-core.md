# Spec: RAG Core cho Doc-Mind (`server/app/core`)

> Trạng thái: Draft — chờ review trước khi implement
> Ngày: 2026-10-12
> Phạm vi: chỉ phần core + CLI để test. Không bao gồm việc nối vào FastAPI router.

---

## 1. Goal

Xây dựng module RAG trong `server/app/core`. Module nhận đầu vào là file PDF (paper tiếng Anh), thực hiện các bước sau:

1. Parse và chunk tài liệu.
2. Embed các chunk bằng `gemini-embedding-2` và lưu vào PostgreSQL (pgvector HNSW + ParadeDB BM25).
3. Truy xuất hybrid: dense + BM25, gộp kết quả bằng RRF.
4. Rerank bằng Laya (`laya-typed-decisions`).
5. Sinh câu trả lời có **citation bắt buộc** bằng `gemini-3.5-flash-lite`.

Toàn bộ luồng chạy được và đo được qua CLI `scripts/rag_cli.py` (`ingest` / `search` / `ask` / `eval`).

---

## 2. Design

### 2.1 Các quyết định đã chốt

| # | Hạng mục | Quyết định |
|---|---|---|
| 1 | BM25 | ParadeDB `pg_search` (BM25 thật, Tantivy), image `paradedb/paradedb:0.26.1-pg17` (đã bundle pgvector) |
| 2 | Embedding | `gemini-embedding-2`, `output_dimensionality=768` |
| 3 | LLM | `gemini-3.5-flash-lite` |
| 4 | Reranker | Laya `aac6fef/laya-typed-decisions-mlx` (chạy MLX trên Mac), mặc định bật; có `NoOpReranker` làm fallback |
| 5 | PDF parser | PyMuPDF (`pymupdf`) |
| 6 | Phạm vi truy vấn | Lọc theo `user_id` (bắt buộc) + `document_ids` (tùy chọn) |
| 7 | Migration | Thêm Alembic ngay. Bỏ `Base.metadata.create_all` |
| 8 | LLM provider | Giữ streaming hiện tại. Thêm chế độ non-stream qua cờ `stream` trong `generate()` |
| 9 | Citation | Bắt buộc. Câu trả lời không có citation hợp lệ bị đánh dấu `grounded=False` |

### 2.2 Các sự thật đã kiểm chứng (ảnh hưởng trực tiếp tới thiết kế)

Kiểm chứng ngày 2026-10-12 bằng API key thật, source code `laya_mlx` 0.4.0 và docs `pg_search` 0.26.1.

- **`gemini-embedding-2`**
  - Hỗ trợ 128–3072 chiều. Vector ở 768 chiều **đã được tự normalize** (norm = 1.0), không cần normalize tay.
  - Input tối đa 8192 token.
  - **Không hỗ trợ `task_type`**: API không báo lỗi nhưng docs nói không dùng. Phải đưa task vào **prefix trong text**:
    - Document: `title: {title} | text: {content}`
    - Query: `task: question answering | query: {q}` (hoặc `task: search result | query: {q}`)
  - **Bẫy batching:** truyền `contents=["a", "b"]` (list string) trả về **1 embedding gộp**. Phải truyền list `types.Content`, mỗi phần tử một `Content`, thì mới nhận được N embedding.
  - Tối đa **100 Content/request**. Free tier đã trả về `429 RESOURCE_EXHAUSTED` với batch 100.
- **`gemini-3.5-flash-lite`**
  - `ThinkingConfig(thinking_budget=0)` trả về **400 INVALID_ARGUMENT**, nên `GeminiProvider` hiện tại sẽ lỗi với model này.
  - `thinking_level="minimal"` / `"low"` chạy được.
- **Laya `predict(state, questions)`**
  - Phần câu hỏi + options bị cắt ở `head_max_len` (mặc định 192 token). Phần còn lại tới `max_len` dành cho `state`. Checkpoint typed-decisions có context 1024.
  - Vì vậy **passage phải nằm trong `state`**, không nằm trong `instructions`.
  - Mỗi lần gọi `predict` chỉ nhận **một state**, nên N candidates = N lần gọi.
  - Câu hỏi kiểu `noul` trả về `answers[qid]["noul"]` = P(true). Kết quả có `usage["truncated"]` để phát hiện passage bị cắt.
- **ParadeDB 0.26.1**
  - Cú pháp tạo index: `USING paradedb (...) WITH (key_field='id')` (`bm25` vẫn là alias).
  - Match OR dùng `|||`, lấy điểm bằng `pdb.score(id)`.
  - Tokenizer cấu hình qua cast, ví dụ `content::pdb.simple('stemmer=english', 'stopwords_language=english')`.
  - Filter trên field `::pdb.literal` được push-down vào index scan.
  - `CREATE EXTENSION pg_search CASCADE` tự bật pgvector.

### 2.3 Luồng dữ liệu

```
INGEST
PDF ─► PyMuPDFLoader ─► ParsedDocument(title, blocks[page, text, is_heading])
    ─► StructuredChunker (TokenCounter=ModernBERT tokenizer)
         target 384 tok, overlap 64 tok, max 512 tok, cắt theo section, bỏ phần References
    ─► GeminiEmbedder.embed_documents  (batch 32, retry/backoff, prefix "title: … | text: …")
    ─► PgChunkRepository.replace_document_chunks  (1 transaction: DELETE cũ + INSERT mới)
    ─► PgDocumentRepository.mark_indexed

QUERY
query ─┬─► PgVectorRetriever  (embed_query ─► HNSW, top 50, filter user/doc)  ─┐
       └─► ParadeDBBM25Retriever (content ||| q, top 50, filter push-down)     ─┴─► ReciprocalRankFusion(k=60) ─► top 30
    ─► LayaReranker (noul P(relevant), top 5, ngưỡng min_score)
         └─ nếu không còn candidate nào ≥ ngưỡng ─► trả về "refused" ngay, KHÔNG gọi LLM
    ─► ContextBuilder (small-to-big: ghép thêm chunk liền kề ±1, merge, đánh số [1..m])
    ─► RAG prompt ─► GeminiProvider.generate(stream=True|False)
    ─► CitationParser ─► Answer(text, citations, grounded, timings)
```

### 2.4 Nguyên tắc kiến trúc (SOLID)

- **SRP:** mỗi file làm một việc: loader, chunker, embedder, dense retriever, sparse retriever, fusion, reranker, context builder, citation parser, answer generator.
- **OCP / DIP:**
  - Pipeline (`IngestionPipeline`, `RAGService`) chỉ phụ thuộc vào `typing.Protocol` trong `core/interfaces.py`.
  - Muốn đổi Laya sang cross-encoder, hay Gemini sang provider khác, chỉ cần viết class mới và sửa `core/factory.py`.
- **ISP:** tách `ChunkWriter` / `ChunkReader` / `DocumentStore` thay vì gộp một repository lớn. `Retriever` chỉ có một method.
- **LSP:** mọi `Reranker` cùng contract: nhận candidates, trả về ≤ `top_n`, giữ nguyên `chunk`, chỉ bổ sung điểm. `NoOpReranker` thay thế được `LayaReranker` mà không phải sửa pipeline.
- **Composition root duy nhất:** `core/factory.py` là nơi **duy nhất** đọc `app.config.settings`. Mọi class trong core nhận tham số qua constructor, không import `settings`. Nhờ vậy test dễ và tái sử dụng được.
- **Domain thuần:** `core/domain.py` chỉ chứa `@dataclass(frozen=True)`, không phụ thuộc SQLAlchemy hay Gemini.
- **Session:** repository và retriever nhận `async_sessionmaker` (không nhận `AsyncSession`). Mỗi thao tác mở session riêng, nhờ đó dense và sparse chạy song song được bằng `asyncio.gather`.
- **Blocking work:** PyMuPDF và Laya (đều CPU/GPU-bound, sync) chạy qua `asyncio.to_thread`. Laya được bảo vệ bằng một `threading.Lock` (một model dùng chung).

### 2.5 Cấu trúc thư mục

```
server/
├── alembic.ini                                   # MỚI
├── alembic/                                      # MỚI (template async)
│   ├── env.py
│   └── versions/
│       ├── 0001_baseline.py                      # users, documents (schema hiện tại)
│       └── 0002_rag_core.py                      # extensions, cột mới cho documents, document_chunks, HNSW, BM25
├── app/
│   ├── config.py                                 # SỬA: thêm nhóm setting RAG
│   ├── db/init_db.py                             # SỬA: bỏ create_all, chỉ seed + kiểm tra alembic_version
│   ├── models/
│   │   ├── __init__.py                           # SỬA: export DocumentChunk
│   │   ├── document.py                           # SỬA: thêm title, status, content_hash, num_pages, num_chunks, error, indexed_at
│   │   └── document_chunk.py                     # MỚI
│   └── core/
│       ├── __init__.py
│       ├── domain.py                             # MỚI: dataclass thuần
│       ├── interfaces.py                         # MỚI: Protocol
│       ├── errors.py                             # MỚI: exception hierarchy
│       ├── factory.py                            # MỚI: composition root
│       ├── rag_service.py                        # MỚI: orchestrator truy vấn
│       ├── ingestion/
│       │   ├── __init__.py
│       │   ├── pdf_loader.py                     # PyMuPDFLoader
│       │   ├── tokenizer.py                      # HFTokenCounter
│       │   ├── chunker.py                        # StructuredChunker
│       │   └── pipeline.py                       # IngestionPipeline
│       ├── embedding/
│       │   ├── __init__.py
│       │   └── gemini_embedder.py
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── chunk_repository.py               # PgChunkRepository (ChunkWriter + ChunkReader)
│       │   └── document_repository.py            # PgDocumentRepository (DocumentStore)
│       ├── retrieval/
│       │   ├── __init__.py
│       │   ├── dense.py                          # PgVectorRetriever
│       │   ├── sparse.py                         # ParadeDBBM25Retriever
│       │   ├── fusion.py                         # ReciprocalRankFusion
│       │   └── hybrid.py                         # HybridRetriever
│       ├── rerank/
│       │   ├── __init__.py
│       │   ├── laya_reranker.py
│       │   └── noop_reranker.py
│       ├── generation/
│       │   ├── __init__.py
│       │   ├── context_builder.py
│       │   ├── citations.py
│       │   └── answer_generator.py
│       ├── llm/
│       │   ├── base.py                           # SỬA: thêm cờ stream (overload)
│       │   ├── gemini_provider.py                # SỬA: thinking_level, non-stream, không nuốt lỗi
│       │   └── post_processor.py                 # giữ nguyên (tái sử dụng cho eval-gen)
│       └── prompt/
│           ├── prompt_templates.py               # giữ nguyên
│           └── rag_prompts.py                    # MỚI
├── scripts/
│   └── rag_cli.py                                # MỚI
├── eval/
│   └── golden.sample.jsonl                       # MỚI: mẫu golden set
└── tests/core/                                   # MỚI: unit test cho phần logic thuần
docker-compose.yml                                # SỬA: image ParadeDB
```

### 2.6 Ngoài phạm vi giai đoạn này

- Nối core vào router `/document/uploadfile` (tự ingest khi upload) và `/conversation` (RAG chat).
- Hội thoại nhiều lượt / viết lại câu hỏi theo lịch sử chat.
- Dịch câu hỏi (ví dụ câu hỏi tiếng Việt trên tài liệu tiếng Anh). Dense search vẫn chạy nhờ embedding đa ngôn ngữ, nhưng BM25 sẽ yếu. Interface `Retriever` cho phép thêm `QueryTransformer` sau.
- OCR cho PDF scan; trích xuất bảng/công thức.
- Tách `ServerSentEvent` ra khỏi core LLM: giữ nguyên theo yêu cầu, ghi nhận là nợ kỹ thuật.

---

## 3. Implementation

### 3.1 Hạ tầng: Docker, Alembic, Settings

**`docker-compose.yml`**

```yaml
services:
  postgres:
    image: paradedb/paradedb:0.26.1-pg17
    container_name: docmind_postgres
    restart: always
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-docmind}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - paradedb_data:/var/lib/postgresql/data
    env_file:
      - server/.env

volumes:
  paradedb_data:
```

> ⚠️ Phải dùng volume mới (`paradedb_data`). Volume `postgres_data` cũ là PG16/alpine, không tương thích với PG17. Dữ liệu dev (users/documents) sẽ phải seed lại.

**Alembic**

- `cd server && uv run alembic init -t async alembic`.
- `env.py`:
  - `config.set_main_option("sqlalchemy.url", settings.db_uri)`.
  - `target_metadata = Base.metadata`; import `app.models` để đăng ký model.
  - `include_object` bỏ qua index `ix_document_chunks_bm25`, vì ORM không biểu diễn được index này. Nếu không bỏ qua, autogenerate sẽ đề xuất drop nó.
- `0001_baseline`: tạo `users`, `documents` đúng như model hiện tại. Với DB cũ đã có bảng: `alembic stamp 0001_baseline`.
- `0002_rag_core` (dùng `op.execute` cho phần ORM không làm được):

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;

ALTER TABLE documents
  ADD COLUMN title        VARCHAR(512),
  ADD COLUMN status       VARCHAR(16) NOT NULL DEFAULT 'pending',
  ADD COLUMN content_hash CHAR(64),
  ADD COLUMN num_pages    INTEGER,
  ADD COLUMN num_chunks   INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN error        TEXT,
  ADD COLUMN indexed_at   TIMESTAMP,
  ADD CONSTRAINT ck_documents_status
      CHECK (status IN ('pending', 'processing', 'indexed', 'failed'));

CREATE TABLE document_chunks (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  document_id   VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  user_id       VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  chunk_index   INTEGER NOT NULL,
  section       TEXT,
  content       TEXT NOT NULL,
  overlap_chars INTEGER NOT NULL DEFAULT 0,
  page_start    INTEGER NOT NULL,
  page_end      INTEGER NOT NULL,
  token_count   INTEGER NOT NULL,
  embedding     vector(768) NOT NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT now(),
  CONSTRAINT uq_document_chunks_document_id_chunk_index UNIQUE (document_id, chunk_index)
);

CREATE INDEX ix_document_chunks_user_id_document_id
  ON document_chunks (user_id, document_id);

CREATE INDEX ix_document_chunks_embedding_hnsw
  ON document_chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX ix_document_chunks_bm25
  ON document_chunks
  USING paradedb (
    id,
    (content::pdb.simple('stemmer=english', 'stopwords_language=english')),
    (user_id::pdb.literal),
    (document_id::pdb.literal)
  )
  WITH (key_field = 'id');
```

- `downgrade()`: đảo ngược (drop index/bảng/cột). Không drop extension.
- Ghi chú thiết kế:
  - `user_id` được denormalize vào `document_chunks` để cả HNSW và BM25 lọc được mà không phải JOIN.
  - `overlap_chars` = số ký tự đầu chunk bị lặp lại từ chunk trước. Dùng để ghép chunk liền kề mà không bị trùng text (mục 3.8).
  - Đổi `embedding_dim` sau này cần migration mới và re-ingest toàn bộ.

**`app/db/init_db.py`**

- Xóa `Base.metadata.create_all`.
- Trước khi seed: `SELECT version_num FROM alembic_version`. Nếu bảng không tồn tại thì raise `RuntimeError("Database chưa được migrate. Chạy: uv run alembic upgrade head")`.

**`app/models/document_chunk.py`**: ORM `DocumentChunk`, dùng `pgvector.sqlalchemy.Vector(768)` cho `embedding`, khai báo HNSW `Index` với `postgresql_using="hnsw"`, `postgresql_with={"m": 16, "ef_construction": 64}`, `postgresql_ops={"embedding": "vector_cosine_ops"}`. **`app/models/document.py`**: thêm các cột ở trên, `to_dict()` trả thêm `title`, `status`, `num_chunks`.

**`app/config.py`**: thêm vào `Settings` (và `.env.example`):

```python
# ---- Gemini ----
gemini_model: str = "gemini-3.5-flash-lite"
gemini_thinking_level: str = "minimal"          # minimal | low | medium | high

# ---- Embedding ----
embedding_model: str = "gemini-embedding-2"
embedding_dim: int = 768                         # phải khớp vector(768) trong migration
embedding_batch_size: int = 32                   # hard limit API = 100
embedding_max_retries: int = 6
embedding_query_task: str = "question answering" # hoặc "search result"

# ---- Chunking ----
chunk_tokenizer: str = "answerdotai/ModernBERT-large"
chunk_target_tokens: int = 384
chunk_overlap_tokens: int = 64
chunk_max_tokens: int = 512
chunk_min_tokens: int = 64
chunk_include_references: bool = False

# ---- Retrieval ----
retrieval_dense_k: int = 50
retrieval_sparse_k: int = 50
retrieval_rrf_k: int = 60
retrieval_dense_weight: float = 1.0
retrieval_sparse_weight: float = 1.0
retrieval_candidates: int = 30                   # số candidate đưa vào reranker
hnsw_ef_search: int = 100

# ---- Rerank ----
reranker: str = "laya"                           # laya | none
laya_model: str = "aac6fef/laya-typed-decisions-mlx"
laya_dtype: str = "float16"
rerank_top_n: int = 5
rerank_min_score: float = 0.10                   # sẽ tune lại bằng eval

# ---- Generation ----
context_window: int = 1                          # số chunk liền kề mỗi phía (small-to-big)
context_max_tokens: int = 6000
```

### 3.2 Domain và Interfaces

**`core/domain.py`**: tất cả là `@dataclass(frozen=True, slots=True)`:

```python
class DocumentStatus(str, Enum): PENDING, PROCESSING, INDEXED, FAILED

TextBlock(page_number: int, text: str, is_heading: bool)
ParsedDocument(title: str, num_pages: int, blocks: tuple[TextBlock, ...])
ChunkDraft(chunk_index: int, content: str, section: str | None,
           page_start: int, page_end: int, token_count: int, overlap_chars: int)
EmbeddedChunk(draft: ChunkDraft, embedding: tuple[float, ...])
SearchScope(user_id: str, document_ids: tuple[str, ...] | None = None)
RetrievedChunk(chunk_id: int, document_id: str, document_name: str, document_title: str | None,
               chunk_index: int, content: str, section: str | None,
               page_start: int, page_end: int, overlap_chars: int)
ScoredChunk(chunk: RetrievedChunk, score: float,
            scores: Mapping[str, float],   # {"dense": .., "sparse": .., "rrf": .., "rerank": ..}
            ranks: Mapping[str, int])      # {"dense": 3, "sparse": 1}
ContextBlock(ref: int, document_id: str, document_name: str, page_start: int, page_end: int,
             section: str | None, text: str, chunk_ids: tuple[int, ...])
Citation(ref: int, document_id: str, document_name: str, page_start: int, page_end: int)
Answer(query: str, text: str, citations: tuple[Citation, ...], contexts: tuple[ContextBlock, ...],
       grounded: bool, refused: bool, timings_ms: Mapping[str, float])

# Event cho answer streaming (thuộc core, không phải SSE)
ContextsEvent(contexts), TokenEvent(text), FinalEvent(answer)
```

`ScoredChunk.with_score(name, value, *, primary=True)` trả về bản sao qua `dataclasses.replace`, giữ lại toàn bộ lịch sử điểm để debug và eval.

**`core/interfaces.py`**: tất cả là `typing.Protocol`:

```python
class DocumentLoader(Protocol):
    def load(self, path: Path) -> ParsedDocument: ...

class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...

class Chunker(Protocol):
    def chunk(self, document: ParsedDocument) -> list[ChunkDraft]: ...

class Embedder(Protocol):
    @property
    def dimension(self) -> int: ...
    async def embed_documents(self, title: str, texts: Sequence[str]) -> list[list[float]]: ...
    async def embed_query(self, query: str) -> list[float]: ...

class DocumentStore(Protocol):
    async def get_or_create(self, user_id: str, name: str) -> DocumentRecord: ...
    async def get(self, document_id: str) -> DocumentRecord | None: ...
    async def list_for_user(self, user_id: str) -> list[DocumentRecord]: ...
    async def mark_processing(self, document_id: str) -> None: ...
    async def mark_indexed(self, document_id: str, *, title: str, num_pages: int,
                           num_chunks: int, content_hash: str) -> None: ...
    async def mark_failed(self, document_id: str, error: str) -> None: ...

class ChunkWriter(Protocol):
    async def replace_document_chunks(self, document_id: str, user_id: str,
                                      chunks: Sequence[EmbeddedChunk]) -> int: ...

class ChunkReader(Protocol):
    async def get_window(self, document_id: str, first_index: int, last_index: int) -> list[RetrievedChunk]: ...
    async def sample(self, scope: SearchScope, n: int) -> list[RetrievedChunk]: ...   # dùng cho eval-gen

class Retriever(Protocol):
    async def retrieve(self, query: str, scope: SearchScope, k: int) -> list[ScoredChunk]: ...

class FusionStrategy(Protocol):
    def fuse(self, ranked: Mapping[str, Sequence[ScoredChunk]], k: int) -> list[ScoredChunk]: ...

class Reranker(Protocol):
    async def rerank(self, query: str, candidates: Sequence[ScoredChunk], top_n: int) -> list[ScoredChunk]: ...
```

(`DocumentRecord` là dataclass trong `domain.py` chứa id, user_id, name, title, status, content_hash, num_chunks.)

**`core/errors.py`**:

```
RAGError
├── DocumentLoadError
├── EmbeddingError
├── RerankerUnavailableError
└── LLMGenerationError
```

### 3.3 Refactor LLM (`core/llm/base.py`, `gemini_provider.py`)

**`base.py`**: dùng Template Method + `@overload`. **Giữ tương thích ngược**: `stream` mặc định là `True`, nên `async for chunk in provider.generate(msg)` trong `routers/conversation/services.py` không phải sửa.

```python
class LLMBase(ABC):
    @overload
    def generate(self, query: str, *, system_instruction: str | None = None,
                 stream: Literal[True] = True) -> AsyncIterator[ServerSentEvent]: ...
    @overload
    def generate(self, query: str, *, system_instruction: str | None = None,
                 stream: Literal[False]) -> Awaitable[LLMResponse]: ...

    def generate(self, query, *, system_instruction=None, stream=True):
        if stream:
            return self._generate_stream(query, system_instruction)
        return self._generate_once(query, system_instruction)

    @abstractmethod
    def _generate_stream(self, query: str, system_instruction: str | None) -> AsyncIterator[ServerSentEvent]: ...

    @abstractmethod
    async def _generate_once(self, query: str, system_instruction: str | None) -> LLMResponse: ...
```

**`gemini_provider.py`**:

- `__init__(self, model_name: str | None = None, *, api_key: str | None = None, thinking_level: str | None = None)`:
  - Mặc định lấy từ `settings` (`gemini_model`, `gemini_api_key`, `gemini_thinking_level`).
  - **Bỏ `load_dotenv`** và biến global `GEMINI_API_KEY`.
- `_build_config(system_instruction)`:
  - `types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level), safety_settings=..., system_instruction=system_instruction, automatic_function_calling=disable)`.
  - **Bỏ `thinking_budget=0`** (gây lỗi 400).
- `_generate_stream`: giữ cơ chế thread + `asyncio.Queue` như hiện tại. **Sửa lỗi nuốt exception**: khi gặp event `error`, phải **yield event `error` ra cho consumer** rồi mới dừng (hiện tại chỉ `break`). Event `done` vẫn không được yield.
- `_generate_once`:
  - Gọi `await self.client.aio.models.generate_content(...)`.
  - Trả về `LLMResponse(text=resp.text, provider="gemini", metadata={"model": ..., "finish_reason": ..., "usage": resp.usage_metadata.model_dump() if resp.usage_metadata else None})`.
  - Exception được bọc thành `LLMGenerationError`.
- Khối `if __name__ == "__main__"` được cập nhật để demo cả hai chế độ.

### 3.4 PDF Loader (`ingestion/pdf_loader.py`)

`PyMuPDFLoader(header_footer_margin: float = 0.06, repeat_threshold: float = 0.5)` implements `DocumentLoader`.

1. `doc = pymupdf.open(path)`. Nếu lỗi hoặc file mã hóa thì raise `DocumentLoadError`.
2. Với mỗi trang: `page.get_text("dict", flags=pymupdf.TEXT_DEHYPHENATE | pymupdf.TEXT_PRESERVE_WHITESPACE, sort=True)`. Chỉ lấy block `type == 0`.
3. Text của block = nối các span theo line (line cách nhau bằng dấu cách). Sau đó:
   - `unicodedata.normalize("NFKC", …)` (tách ligature: `ﬁ` → `fi`).
   - Xóa `\x00` (Postgres TEXT không chấp nhận).
   - Gộp khoảng trắng liên tiếp.
4. **Bỏ header/footer**: block nằm trong 6% trên/dưới của trang, có text (sau khi bỏ chữ số) lặp lại trên ≥ 50% số trang, hoặc chỉ là số trang (`^\d+$`).
5. **Phát hiện heading**:
   - Tính `body_size` = cỡ font phổ biến nhất, tính theo trọng số số ký tự.
   - Block là heading nếu là 1 dòng, dài ≤ 120 ký tự, và thỏa ít nhất một trong các điều kiện:
     - `max_span_size ≥ body_size * 1.15`;
     - khớp `^(\d+(\.\d+)*\.?|[IVX]+\.)\s+[A-Z]`;
     - (bỏ số thứ tự rồi lowercase) thuộc `{abstract, introduction, related work, background, method, methods, methodology, experiments, results, discussion, conclusion, conclusions, references, bibliography, acknowledgments, acknowledgements, appendix}`.
6. **Title**:
   - Ưu tiên `doc.metadata["title"]` nếu không rỗng và không phải tên file hay "untitled".
   - Nếu không có: span có font lớn nhất ở nửa trên trang 1.
   - Nếu vẫn không có: `path.stem`.
7. Trả về `ParsedDocument(title, num_pages, blocks)`. Nếu tổng text < 200 ký tự thì raise `DocumentLoadError("PDF có vẻ là bản scan, chưa hỗ trợ OCR")`.

Toàn bộ là sync. Pipeline gọi qua `asyncio.to_thread`.

### 3.5 Token counter và Chunker (`ingestion/tokenizer.py`, `ingestion/chunker.py`)

**`HFTokenCounter(model_id: str)`**:
- Dùng `tokenizers.Tokenizer.from_pretrained(model_id)`, `count(text) = len(encode(text, add_special_tokens=False).ids)`.
- Dùng ModernBERT tokenizer vì Laya được build trên ModernBERT. Đo theo token của reranker đảm bảo passage không bị cắt khi rerank. Token Gemini luôn dư (giới hạn 8192).

**`StructuredChunker(counter, target_tokens=384, overlap_tokens=64, max_tokens=512, min_tokens=64, include_references=False)`**:

1. Duyệt `blocks` theo thứ tự. Heading mở một **section** mới (`section = heading.text`).
2. Nếu heading là `references`/`bibliography` và `include_references=False`: bỏ qua mọi block cho tới khi gặp heading chứa `appendix` (không phân biệt hoa thường).
3. Trong mỗi section, tách từng block thành câu bằng regex `(?<=[.!?])\s+(?=[A-Z0-9(\[])`, có danh sách viết tắt không được cắt: `et al.`, `e.g.`, `i.e.`, `Fig.`, `Figs.`, `Eq.`, `Eqs.`, `Sec.`, `Tab.`, `vs.`, `cf.`, `No.`. Mỗi câu mang theo `page_number`.
4. Câu dài hơn `max_tokens` thì cắt cứng theo token (dùng offsets của tokenizer) thành các đoạn ≤ `max_tokens`.
5. **Đóng gói**:
   - Cộng dồn câu tới khi thêm câu kế tiếp sẽ vượt `target_tokens` thì emit chunk.
   - Chunk tiếp theo **bắt đầu bằng các câu cuối của chunk trước**, tổng ≤ `overlap_tokens`. `overlap_chars` = độ dài phần text lặp lại, tính cả dấu cách nối.
   - Sang section mới thì flush, **không overlap qua ranh giới section**.
6. Chunk cuối của section có < `min_tokens`: gộp vào chunk trước nếu tổng ≤ `max_tokens`.
7. `page_start` / `page_end` = min/max page của các câu trong chunk. `chunk_index` tăng dần trên toàn tài liệu, bắt đầu từ 0.
8. **Bất biến (unit test)**: mọi chunk có `token_count ≤ max_tokens`; `content[overlap_chars:]` nối lại theo thứ tự tái tạo được toàn bộ text đã giữ của section (sai khác tối đa ở khoảng trắng).

### 3.6 Embedder (`embedding/gemini_embedder.py`)

`GeminiEmbedder(client: genai.Client, model="gemini-embedding-2", dimension=768, batch_size=32, max_retries=6, query_task="question answering")`.

- Kiểm tra `1 ≤ batch_size ≤ 100` ngay trong constructor.
- `embed_documents(title, texts)`:
  - Mỗi text được format thành `f"title: {title or 'none'} | text: {text}"`.
  - Chia batch; mỗi batch là `contents=[types.Content(parts=[types.Part.from_text(text=t)]) for t in batch]` — **bắt buộc dùng Content riêng** (xem 2.2).
  - Gọi `await client.aio.models.embed_content(model=..., contents=..., config=types.EmbedContentConfig(output_dimensionality=dimension))`.
- `embed_query(query)`: format `f"task: {query_task} | query: {query}"`, gọi 1 lần.
- **Text cho embedding của chunk**: `f"{section}\n{content}"` nếu có section, ngược lại `content` (contextual header rẻ).
- **Retry**: dùng `tenacity`, `retry_if_exception(lambda e: isinstance(e, genai.errors.APIError) and e.code in {429, 500, 502, 503, 504})`, `wait_exponential_jitter(initial=2, max=60)`, `stop_after_attempt(max_retries)`. Hết retry thì raise `EmbeddingError`.
- **Validate**: `len(result.embeddings) == len(batch)` và mỗi vector có `len == dimension`. Sai thì raise `EmbeddingError`, vì lỗi này nghĩa là bẫy batching hoặc cấu hình dimension sai.
- Log loguru: số batch, tổng thời gian.

### 3.7 Storage (`storage/chunk_repository.py`, `storage/document_repository.py`)

**`PgChunkRepository(session_factory)`** implements `ChunkWriter` + `ChunkReader`:

- `replace_document_chunks`: trong **một transaction**:
  - `DELETE FROM document_chunks WHERE document_id = :id`.
  - Bulk `INSERT` (`session.execute(insert(DocumentChunk), rows)`).
  - Trả về số dòng đã insert. Re-ingest an toàn và idempotent.
- `get_window(document_id, first, last)`: `chunk_index BETWEEN :first AND :last ORDER BY chunk_index`, JOIN `documents` để lấy `name`, `title`.
- `sample(scope, n)`: `ORDER BY random() LIMIT :n` có filter theo scope (chỉ dùng cho eval-gen).

**`PgDocumentRepository(session_factory)`** implements `DocumentStore`:

- `get_or_create(user_id, name)`: tìm theo `(user_id, name)`; chưa có thì tạo `status='pending'`. Theo quy ước của `cruds/document.py`, `name` là tên file bỏ phần mở rộng.
- `mark_*`: cập nhật `status`, `error`, `indexed_at = utcnow()` và các trường liên quan.

### 3.8 Retrieval

**`retrieval/dense.py` — `PgVectorRetriever(session_factory, embedder, ef_search=100)`**:

```sql
-- chạy trong cùng transaction:
SET LOCAL hnsw.ef_search = 100;
SET LOCAL hnsw.iterative_scan = relaxed_order;   -- tránh thiếu kết quả khi có filter

WITH nn AS MATERIALIZED (
  SELECT id, embedding <=> CAST(:qvec AS vector) AS distance
  FROM document_chunks
  WHERE user_id = :user_id
    [AND document_id IN :document_ids]            -- bindparam(expanding=True), chỉ thêm khi có
  ORDER BY embedding <=> CAST(:qvec AS vector)
  LIMIT :k
)
SELECT c.id, c.document_id, d.name, d.title, c.chunk_index, c.content, c.section,
       c.page_start, c.page_end, c.overlap_chars, 1 - nn.distance AS score
FROM nn
JOIN document_chunks c ON c.id = nn.id
JOIN documents d ON d.id = c.document_id
ORDER BY nn.distance, c.id;                        -- sắp lại vì relaxed_order không đảm bảo thứ tự
```

- `SET LOCAL` không nhận bind param, nên `ef_search` được ép kiểu `int` rồi mới format vào câu lệnh.
- `qvec` là chuỗi `'[x1,x2,...]'`.
- Kết quả: `ScoredChunk(score=cosine_sim, scores={"dense": sim}, ranks={"dense": i+1})`.

**`retrieval/sparse.py` — `ParadeDBBM25Retriever(session_factory)`**:

```sql
WITH hits AS (
  SELECT id, pdb.score(id) AS score
  FROM document_chunks
  WHERE content ||| CAST(:q AS text)
    AND user_id = :user_id
    [AND document_id IN :document_ids]
  ORDER BY pdb.score(id) DESC, id
  LIMIT :k
)
SELECT c.…, d.name, d.title, hits.score
FROM hits
JOIN document_chunks c ON c.id = hits.id
JOIN documents d ON d.id = c.document_id
ORDER BY hits.score DESC, c.id;
```

- Query luôn được truyền qua bind param, không nối chuỗi.
- `|||` tokenize query bằng tokenizer của index (stem + stopword), nên không có rủi ro query-syntax injection.
- Query rỗng hoặc chỉ toàn khoảng trắng thì trả `[]` mà không chạm DB.

**`retrieval/fusion.py` — `ReciprocalRankFusion(k=60, weights={"dense": 1.0, "sparse": 1.0})`**:

- `score(id) = Σ_branch weight_b / (k + rank_b(id))`, rank bắt đầu từ 1.
- Gộp `scores`/`ranks` của các nhánh vào một `ScoredChunk`. Sắp xếp theo `rrf` giảm dần, hòa điểm thì xếp theo `chunk_id`, cắt còn `k_out`.
- Thuần Python, không I/O, có unit test.

**`retrieval/hybrid.py` — `HybridRetriever(dense, sparse, fusion, dense_k, sparse_k)`** implements `Retriever`:
- Chạy `asyncio.gather(dense.retrieve(q, scope, dense_k), sparse.retrieve(q, scope, sparse_k))`, rồi `fusion.fuse({"dense": d, "sparse": s}, k)`.

> Vì sao fuse trong Python thay vì một câu SQL RRF như docs ParadeDB: các nhánh độc lập, test được riêng, đổi chiến lược fusion không phải sửa SQL, và CLI `search --mode dense|sparse` dùng lại đúng các class này. Chi phí thêm chỉ là ~100 dòng truyền qua mạng. Nếu cần tối ưu sau này có thể thêm `SqlHybridRetriever` mà không phải sửa pipeline.

### 3.9 Reranker

**`rerank/laya_reranker.py` — `LayaReranker(model_id, dtype="float16", batch_size=16, question=DEFAULT_QUESTION)`**:

- `import laya_mlx` được **lazy import** trong `_load()`. Nếu `ImportError` thì raise `RerankerUnavailableError("laya-mlx chỉ chạy trên Apple Silicon; đặt RERANKER=none")`.
- Model được load **một lần** (lazy, có `threading.Lock`), dùng `laya.load(model_id, dtype=dtype, batch_size=batch_size, cache_prompts=True)`. Lần đầu sẽ tải checkpoint từ HuggingFace.
- Mỗi candidate:

```python
DEFAULT_QUESTION = {
    "relevant": {
        "type": "noul",
        "instructions": "Does the passage contain information that answers the question?",
    }
}
state = {"question": query, "passage": f"{section}\n{content}" if section else content}
result = agent.predict(state, DEFAULT_QUESTION)
score = result["answers"]["relevant"]["noul"]       # P(true) ∈ [0, 1]
if result["usage"]["truncated"]: logger.warning(...)  # passage bị cắt → nên giảm chunk_max_tokens
```

- Instruction cố định, câu hỏi và passage nằm trong `state`. Lý do: phần instruction bị cắt ở 192 token; giữ instruction cố định thì `cache_prompts=True` cache được prefix.
- Toàn bộ vòng lặp chạy trong `asyncio.to_thread`, có lock.
- Kết quả: `with_score("rerank", p)`, sắp xếp theo `rerank` giảm dần (hòa thì xếp theo `rrf`), cắt còn `top_n`.
- Ghi timing tổng và trung bình mỗi candidate.
- Phương án thay thế chưa làm, có thể bật qua tham số `question`: kiểu `score` với rubric `["irrelevant", "partially relevant", "directly answers"]`, chuẩn hóa `score/2`. Eval quyết định chọn phương án nào.

**`rerank/noop_reranker.py` — `NoOpReranker`**: trả về `candidates[:top_n]`, giữ nguyên thứ tự RRF, `with_score("rerank", c.score)`.

**Ngưỡng**: `RAGService` lọc bỏ candidate có `scores["rerank"] < rerank_min_score`. Với `NoOpReranker`, ngưỡng không được áp dụng (`min_score=None`).

### 3.10 Generation

**`generation/context_builder.py` — `ContextBuilder(chunk_reader, window=1, max_tokens=6000, counter)`**:

1. Với mỗi chunk trong top-n (đã có thứ tự rerank), lấy khoảng `[chunk_index - window, chunk_index + window]` qua `get_window`.
2. Gộp các khoảng **giao nhau hoặc liền kề trong cùng document** thành một block. Text block = `chunks[0].content + "".join(c.content[c.overlap_chars:] for c in chunks[1:])`, nhờ đó không lặp text do overlap.
3. Thứ tự block = thứ tự rerank tốt nhất của chunk gốc bên trong block. Đánh số `ref` từ 1.
4. Cộng dồn token tới `max_tokens`. Block vượt ngân sách sẽ bị loại (không cắt giữa chừng). Block đầu tiên luôn được giữ.

**`prompt/rag_prompts.py`**:

```python
REFUSAL_TEXT = "I couldn't find information about this in the provided documents."

RAG_SYSTEM_PROMPT = """You are Doc-Mind, an assistant that answers questions strictly from the provided document excerpts.

Rules:
1. Use ONLY the information in the numbered sources below. Do not use prior knowledge.
2. Every factual sentence MUST end with at least one citation in the form [n], where n is the source number. Use multiple citations like [1][3] when combining sources.
3. If the sources do not contain the answer, reply exactly: "{refusal}"
4. Do not invent source numbers. Do not cite a source that does not support the sentence.
5. Answer in the same language as the question. Be concise and precise; prefer the paper's own terminology.
"""

def build_rag_user_prompt(question: str, contexts: Sequence[ContextBlock]) -> str:
    # Sources:
    # [1] "<document title or name>", pages 3-4, section "3.2 Scaled Dot-Product Attention"
    # <text>
    #
    # [2] ...
    #
    # Question: <question>
```

**`generation/citations.py`**:
- `parse_refs(text) -> list[int]`: regex `\[(\d+)\]`, giữ thứ tự xuất hiện đầu tiên, bỏ trùng.
- `build_citations(text, contexts) -> (citations, invalid_refs)`: ref không nằm trong `1..len(contexts)` thì cho vào `invalid_refs`.
- `is_grounded(text, citations, invalid_refs)`: `True` khi có ≥ 1 citation hợp lệ và `invalid_refs` rỗng. Riêng câu trả lời đúng bằng `REFUSAL_TEXT` thì `refused=True`, `grounded=True`.

**`generation/answer_generator.py` — `AnswerGenerator(llm: LLMBase)`**:
- `async def generate(question, contexts) -> tuple[str, dict]`: gọi `llm.generate(prompt, system_instruction=..., stream=False)`.
- `async def stream(question, contexts) -> AsyncIterator[str]`: duyệt `llm.generate(..., stream=True)`. Event `message` thì yield `data`; event `error` thì raise `LLMGenerationError(data)`.

### 3.11 Orchestrators

**`ingestion/pipeline.py` — `IngestionPipeline(loader, chunker, embedder, documents: DocumentStore, chunks: ChunkWriter)`**:

```python
async def ingest(self, path: Path, user_id: str, *, force: bool = False) -> IngestReport:
    content_hash = sha256(path.read_bytes())
    doc = await documents.get_or_create(user_id, path.stem)
    if doc.status == INDEXED and doc.content_hash == content_hash and not force:
        return IngestReport(skipped=True, ...)
    await documents.mark_processing(doc.id)
    try:
        parsed = await asyncio.to_thread(loader.load, path)
        drafts = await asyncio.to_thread(chunker.chunk, parsed)
        vectors = await embedder.embed_documents(parsed.title, [embed_text(d) for d in drafts])
        n = await chunks.replace_document_chunks(doc.id, user_id, [EmbeddedChunk(d, tuple(v)) ...])
        await documents.mark_indexed(doc.id, title=parsed.title, num_pages=parsed.num_pages,
                                     num_chunks=n, content_hash=content_hash)
    except Exception as e:
        await documents.mark_failed(doc.id, f"{type(e).__name__}: {e}")
        raise
    return IngestReport(document_id=doc.id, num_pages=..., num_chunks=n, timings_ms={load, chunk, embed, store})
```

**`rag_service.py` — `RAGService(retriever, reranker, context_builder, generator, candidates=30, top_n=5, min_score=0.1)`**:

- `async def search(query, scope, *, rerank=True, k=None) -> SearchResult(chunks, timings_ms)`: retrieve `candidates` → (rerank → lọc theo ngưỡng) hoặc cắt `k`.
- `async def answer(query, scope) -> Answer`:
  - `search`; nếu rỗng thì trả `Answer(text=REFUSAL_TEXT, refused=True, grounded=True, citations=())`, **không gọi LLM**.
  - Ngược lại: `contexts` → `generate` → citations → `Answer`.
- `async def answer_stream(query, scope) -> AsyncIterator[ContextsEvent | TokenEvent | FinalEvent]`: cùng luồng như trên; yield `ContextsEvent` trước, sau đó từng `TokenEvent`, cuối cùng `FinalEvent` với citation đã parse.
- `timings_ms` gồm các khóa: `embed_query`, `dense`, `sparse`, `fusion`, `rerank`, `context`, `llm`, `total`.

`RAGService` nhận một `Retriever` bất kỳ. CLI `search --mode dense` truyền thẳng `PgVectorRetriever` vào, không cần class mới.

### 3.12 Composition root (`core/factory.py`)

```python
def build_embedder(s: Settings = settings) -> GeminiEmbedder
def build_retriever(mode: Literal["dense", "sparse", "hybrid"], s=settings) -> Retriever
def build_reranker(name: str | None = None, s=settings) -> Reranker   # "laya" | "none"
def build_ingestion_pipeline(s=settings) -> IngestionPipeline
def build_rag_service(*, mode="hybrid", reranker: str | None = None, s=settings) -> RAGService
```

- Dùng chung `AsyncSessionLocal` từ `app.db.session` và một `genai.Client(api_key=s.gemini_api_key)`.
- `LayaReranker` và `HFTokenCounter` được cache bằng `functools.lru_cache` theo `model_id`, tránh load lại model.

### 3.13 CLI (`server/scripts/rag_cli.py`)

- Dùng `argparse` với subcommand. Theo idiom của `scripts/seed.py`: thêm `SERVER_DIR` vào `sys.path`.
- Chạy bằng `cd server && uv run python scripts/rag_cli.py <cmd>`.
- `--user` nhận **username** (mặc định `settings.first_superuser`); CLI tự tra ra `user_id`.

| Lệnh | Mô tả | Output |
|---|---|---|
| `ingest PATH [PATH…] [--user admin] [--force]` | Ingest một hoặc nhiều PDF (glob được) | Mỗi file: `id`, title, pages, chunks, timings; tổng kết số OK / skipped / failed |
| `docs [--user admin]` | Liệt kê tài liệu | Bảng `id | name | title | status | chunks | indexed_at` |
| `chunks DOC_ID [--limit 5]` | Xem chunk đã lưu (debug chunker) | index, pages, section, tokens, 200 ký tự đầu |
| `search "Q" [--mode dense\|sparse\|hybrid] [--rerank/--no-rerank] [-k 10] [--doc ID …] [--json]` | Chỉ retrieval | Bảng: rank, doc, pages, section, score theo từng nhánh (`dense`/`sparse`/`rrf`/`rerank`), snippet; cuối cùng là timings |
| `ask "Q" [--doc ID …] [--no-stream] [--show-context] [--reranker laya\|none]` | RAG đầy đủ | Câu trả lời (stream ra terminal), danh sách Sources `[n] doc — p.x–y`, `grounded`/`refused`, timings |
| `eval-gen --doc ID [--n 20] -o eval/golden.jsonl` | Sinh golden set tổng hợp | File JSONL |
| `eval GOLDEN.jsonl [--k 1,3,5,10] [--modes dense,sparse,hybrid,hybrid+rerank]` | Đo chất lượng retrieval | Bảng metric theo mode × k và latency trung bình |

- Mã thoát: `0` thành công, `1` lỗi nghiệp vụ (`RAGError`), `2` lỗi tham số.
- Lỗi được in ra dạng một dòng `ERROR: …`. Thêm `--debug` để in traceback.

**Định dạng golden set (JSONL)**:

```json
{"id": "q001", "question": "What is the dimensionality of the keys in the base Transformer?", "document_name": "attention_is_all_you_need", "relevant_pages": [5], "source_chunk_id": 42}
```

**Eval**:
- Một chunk được coi là đúng nếu `document_name` khớp **và** `[page_start, page_end]` giao với `relevant_pages`. Chấm theo trang vì `chunk_id` thay đổi sau mỗi lần re-ingest.
- Metrics:
  - `Hit@k` — có ≥ 1 kết quả đúng trong top-k.
  - `MRR@k`.
  - `PageRecall@k` — tỷ lệ `relevant_pages` được phủ bởi top-k.
- In thêm latency p50 của từng mode.

**`eval-gen`**:
- Lấy ngẫu nhiên `n` chunk qua `ChunkReader.sample`. Với mỗi chunk, gọi LLM (non-stream) với prompt: *"Write one specific question answerable only from this passage. Return JSON {"question": "..."}"*.
- Parse bằng `PostProcessor().process(..., return_json=True)` có sẵn.
- `relevant_pages = range(page_start, page_end + 1)`.
- ⚠️ Câu hỏi sinh tự động thường dùng lại từ ngữ của passage, nên có xu hướng **thiên vị BM25**. Nên bổ sung 10–20 câu hỏi viết tay, diễn đạt khác đi (paraphrase).

### 3.14 Unit tests (`server/tests/core/`)

Chỉ test logic thuần, không cần DB/API:

- `test_fusion.py`:
  - RRF đúng công thức.
  - Chunk chỉ xuất hiện ở một nhánh vẫn được tính điểm.
  - Weights có tác dụng.
  - Hòa điểm xếp theo `chunk_id`.
- `test_chunker.py` (dùng `FakeTokenCounter`: đếm theo từ):
  - Bất biến `≤ max_tokens`.
  - Overlap đúng và `overlap_chars` tái tạo được text.
  - Không overlap qua section.
  - Bỏ References rồi bắt lại ở Appendix.
  - Gộp đuôi nhỏ.
  - Câu cực dài bị cắt cứng.
- `test_context_builder.py` (fake `ChunkReader`): gộp khoảng liền kề, không lặp text overlap, thứ tự theo rerank, ngân sách token.
- `test_citations.py`: parse `[1][3]`, phát hiện ref không hợp lệ, xử lý câu từ chối, câu trả lời không có citation thì `grounded=False`.
- `test_gemini_embedder.py` (mock `client.aio.models.embed_content`):
  - Chia batch đúng, mỗi phần tử là `Content` riêng.
  - Có prefix.
  - Retry khi gặp 429.
  - Raise `EmbeddingError` khi số embedding trả về ≠ số input.

---

## 4. Dependencies

Sửa `server/pyproject.toml`:

```toml
dependencies = [
    # ... giữ nguyên các dòng hiện có, trừ laya-mlx ...
    "alembic>=1.16",
    "pgvector>=0.4.1",            # pgvector.sqlalchemy.Vector
    "pymupdf>=1.26",              # ⚠️ AGPL-3.0
    "tokenizers>=0.21",           # đếm token cho chunker (trước đây chỉ có gián tiếp qua laya-mlx)
    "tenacity>=9.0",              # retry cho embedding (khai báo tường minh)
    "laya-mlx>=0.4.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
]
```

- `laya-mlx` có platform marker: trên Mac được cài tự động; trên Linux/Docker bỏ qua, khi đó đặt `RERANKER=none`.
- Đề xuất xóa `google-generativeai` (SDK cũ, đã ngừng phát triển). Hiện không còn import nào trong `app/`; mọi code dùng `google-genai`.
- Hạ tầng: image Docker `paradedb/paradedb:0.26.1-pg17` (gồm `pg_search` 0.26.1 + pgvector).
- Model tải lần đầu (HuggingFace): `aac6fef/laya-typed-decisions-mlx`, tokenizer `answerdotai/ModernBERT-large`.
- Lệnh cài: `cd server && uv add alembic "pgvector>=0.4.1" "pymupdf>=1.26" "tokenizers>=0.21" "tenacity>=9.0"`, sau đó sửa tay dòng `laya-mlx` để thêm marker và chạy `uv sync`.

---

## 5. Verification checklist

**Hạ tầng**
- [ ] `docker compose up -d` → `psql -c "SELECT extname, extversion FROM pg_extension"` có `vector` và `pg_search` (sau khi migrate).
- [ ] `uv run alembic upgrade head` chạy trên DB trống không lỗi; `uv run alembic downgrade 0001_baseline` rồi `upgrade head` lại không lỗi.
- [ ] `uv run alembic check` (autogenerate) báo không có thay đổi; index BM25 không bị đề xuất drop.
- [ ] `uv run python scripts/seed.py` seed được admin. Server khởi động khi chưa migrate thì báo lỗi rõ ràng.
- [ ] `\d document_chunks` có `ix_document_chunks_embedding_hnsw` (hnsw) và `ix_document_chunks_bm25` (paradedb).

**LLM**
- [ ] `uv run python -m app.core.llm.gemini_provider`: stream ra text với `gemini-3.5-flash-lite`, không còn lỗi 400.
- [ ] `generate(q, stream=False)` trả về `LLMResponse` có text và usage.
- [ ] Đặt API key sai → consumer stream nhận được event `error` (không còn trả về rỗng im lặng).
- [ ] Endpoint `/conversation` hiện tại vẫn stream bình thường (tương thích ngược).

**Ingestion**
- [ ] `rag_cli.py ingest <paper>.pdf` → `status=indexed`, `num_chunks > 0`. `chunks <id>` cho thấy section hợp lý, không có header/footer, không có phần References.
- [ ] Ingest lại cùng file → `skipped`. `--force` → số chunk như cũ, không trùng dòng.
- [ ] `SELECT max(token_count) FROM document_chunks` ≤ 512.
- [ ] `SELECT count(*) FROM document_chunks WHERE content LIKE '%' || chr(0) || '%'` = 0.
- [ ] PDF hỏng hoặc bản scan → `status=failed`, có `error`, CLI thoát mã 1.
- [ ] Xóa document qua `DELETE /document/{id}` → chunk của nó bị xóa theo (cascade).

**Retrieval**
- [ ] `search "<câu có từ khóa hiếm trong paper>" --mode sparse` → chunk chứa từ khóa đứng top 3.
- [ ] `search "<câu diễn đạt khác, không trùng từ>" --mode dense` → trả về chunk đúng ý.
- [ ] `--mode hybrid` hiển thị đủ cột `dense`/`sparse`/`rrf`; chunk chỉ có ở một nhánh vẫn xuất hiện.
- [ ] `EXPLAIN` câu dense có `Index Scan using ix_document_chunks_embedding_hnsw`; câu sparse có `Custom Scan (ParadeDB …)`.
- [ ] `--doc <id>` chỉ trả về chunk của tài liệu đó; user khác không thấy chunk của admin.

**Rerank**
- [ ] `search … --rerank` load Laya một lần, cột `rerank` ∈ [0, 1], không có warning `truncated`.
- [ ] Rerank 30 candidates trên Mac mất < 2s (ghi lại con số thực tế vào spec).
- [ ] `--reranker none` chạy được. Giả lập không import được `laya_mlx` → báo `RerankerUnavailableError` rõ ràng.

**Answer**
- [ ] `ask "<câu hỏi có trong paper>"` → câu trả lời có `[n]`, phần Sources khớp trang thật, `grounded=True`.
- [ ] `ask "<câu hỏi ngoài tài liệu, ví dụ thời tiết>"` → `REFUSAL_TEXT`, `refused=True`. Nếu bị chặn bởi ngưỡng thì timings không có `llm`.
- [ ] `ask … --no-stream` và chế độ stream cho cùng một bộ citations.

**Eval và tests**
- [ ] `eval-gen --doc <id> --n 20` tạo được 20 dòng JSONL hợp lệ.
- [ ] `eval eval/golden.jsonl` in bảng cho 4 mode. Ghi kết quả baseline vào spec. Kỳ vọng `hybrid ≥ max(dense, sparse)` về Hit@5. Nếu `hybrid+rerank` không cải thiện MRR@5 so với `hybrid` → xem lại câu hỏi Laya (`noul` vs `score`) hoặc ngưỡng.
- [ ] Tune `rerank_min_score` dựa trên phân phối điểm rerank của câu hỏi có đáp án và câu hỏi ngoài tài liệu.
- [ ] `uv run pytest tests/core -v` pass toàn bộ.
- [ ] `make quality` (black / isort / flake8) pass cho các file mới.

---

## 6. Rủi ro và lưu ý

| Rủi ro | Giảm thiểu |
|---|---|
| Laya không được train cho relevance ranking, chất lượng chưa rõ | Đo bằng `eval` so với `NoOpReranker`; có sẵn phương án `score` rubric; có thể đổi sang cross-encoder chỉ bằng `factory` |
| Quota free tier của embedding (đã gặp 429) | batch 32 + exponential backoff có jitter; batch có thể chỉnh qua `.env` |
| Thứ tự đọc PDF 2 cột | `sort=True` của PyMuPDF đủ cho đa số paper; kiểm tra bằng lệnh `chunks` |
| PyMuPDF và ParadeDB đều là AGPL-3.0 | Ổn cho demo; cần review license trước khi thương mại hóa |
| Đổi `embedding_dim` hoặc embedding model | Bắt buộc migration mới + `ingest --force` toàn bộ |
| Câu hỏi tiếng Việt trên tài liệu tiếng Anh | Dense vẫn chạy được (embedding đa ngôn ngữ); BM25 yếu → giai đoạn sau thêm `QueryTransformer` (dịch câu hỏi) |
