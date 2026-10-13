# Spec: Document & Conversation API + Client integration

> Trạng thái: Draft, chờ review trước khi implement
> Ngày: 2026-10-13
> Branch: `feat/build-document-endpoints`
> Tiền đề: `docs/specs/rag-core.md` đã hoàn thành (core + CLI).

---

## 1. Goal

Nối RAG core vào HTTP API và UI:

1. Upload PDF → file được lưu theo user → hàng đợi Postgres tự động ingest (parse, chunk, embed, lưu pgvector + BM25). Client thấy trạng thái `pending → processing → indexed | failed`.
2. Hội thoại có lưu lịch sử, gắn với 1..N tài liệu đã chọn, hỗ trợ nhiều lượt (câu follow-up được viết lại thành câu độc lập), stream câu trả lời có citation qua SSE.
3. Mọi endpoint dữ liệu người dùng đều yêu cầu JWT và lọc theo chủ sở hữu.
4. Hệ thống chịu được nhiều người chat và upload đồng thời: concurrency có giới hạn, không giữ DB connection khi stream, không tạo thread mỗi request, ingest worker scale ngang được.

---

## 2. Design

### 2.1 Các quyết định đã chốt

| # | Hạng mục | Quyết định |
|---|---|---|
| 1 | Ingest sau upload | **Postgres làm hàng đợi**: bảng `documents` (status `pending`) chính là queue. Worker claim job bằng `FOR UPDATE SKIP LOCKED`. Mặc định chạy trong lifespan của API; có thể tách thành process riêng (`scripts/ingest_worker.py`) để scale |
| 2 | Lịch sử chat | Lưu DB (`conversations`, `messages`) + multi-turn: nếu có lịch sử thì gọi flash-lite non-stream để viết lại câu follow-up trước khi retrieve |
| 3 | Phạm vi hội thoại | Mỗi hội thoại gắn với **1..10 tài liệu** (đã `indexed` lúc tạo). Scope cố định theo hội thoại |
| 4 | Reranker cho API | Setting mới `api_reranker = "none"` (RRF + ngưỡng dense). Laya chỉ dùng cho CLI/eval. Lý do: Laya chạy tuần tự sau một lock, là điểm nghẽn khi tải cao |
| 5 | LLM streaming | Bỏ cơ chế thread + `asyncio.Queue`. Dùng `client.aio.models.generate_content_stream`: không tốn một OS thread cho mỗi request, và hủy được khi client ngắt kết nối |
| 6 | Lưu file | `DOCUMENTS_FOLDER/{user_id}/{name}.pdf`. `name` = tên **đã chuẩn hóa** (NFC, thay ký tự cấm, ≤ 200 byte UTF-8, xem 3.4). Path luôn dựng từ `documents.name` đã lưu, không dựng từ filename client gửi lên |
| 7 | Upload lại cùng tên | So khớp **không phân biệt hoa/thường**: unique `(user_id, lower(name))`. Hash giống → `unchanged`; hash khác → thay file + `pending` (re-ingest), giữ nguyên cách viết hoa/thường của `name` cũ; đang `processing` → `busy` |
| 7b | Cơ chế upload | Giữ multipart nhiều file (`POST /uploadfile`), nhưng endpoint **không khai báo `UploadFile`**: nhận `Request`, kiểm tra auth → `Content-Length` → semaphore → dung lượng trống → quota, rồi mới gọi `request.form(max_files=…)` |
| 7c | Giới hạn tài nguyên | Semaphore upload mỗi process (503), ngưỡng dung lượng trống của volume (507), quota theo user về số byte và số document (409 `quota_exceeded`) |
| 8 | Trạng thái ingest trên UI | Client polling `GET /document` mỗi 3s khi còn document `pending/processing`. Không dùng SSE/WebSocket cho phần này |
| 9 | Endpoint cũ `POST /conversation/stream` | **Xóa** (không có auth, không dùng RAG, client không gọi tới) |

### 2.2 Phân tích tải (vì sao thiết kế như dưới)

| Điểm nghẽn hiện tại | Hậu quả khi nhiều request | Cách xử lý |
|---|---|---|
| `LayaReranker` + `threading.Lock` | Mọi câu hỏi xếp hàng rerank, ~1–2s mỗi câu → p99 tăng tuyến tính theo số user | `api_reranker=none` |
| `GeminiProvider._generate_stream` tạo một daemon thread cho mỗi request | Mỗi stream tốn một OS thread; client ngắt kết nối thì thread vẫn chạy tiếp và vẫn tốn quota | SDK async `aio.models.generate_content_stream` |
| `get_current_user` dùng `get_db` | Session của request có thể giữ connection suốt thời gian stream SSE. Pool mặc định chỉ có 5+10 | `get_current_user` tự mở session ngắn; pool đọc từ settings |
| `embed_query` retry tối đa 6 lần, backoff tới 60s | Gặp 429 thì user chờ hàng phút | Embedder riêng cho phía query: `embedding_query_max_retries=2` |
| Ingest qua `BackgroundTasks` (phương án bị loại) | Job mất khi restart, không scale ngang | Postgres queue + reclaim job treo + giới hạn số lần thử |
| Upload đọc cả file vào RAM (`await file.read()`) | 50 file × 25MB = 1.25GB RAM | Copy theo khối 1 MiB, hash trong lúc copy |
| Endpoint khai báo `files: List[UploadFile]` | FastAPI chạy `await request.form()` (`fastapi/routing.py:430`) **trước** `solve_dependencies` (dòng 481, gồm cả auth). Starlette spool mỗi file vào `SpooledTemporaryFile(1MB)` → thư mục temp, **không giới hạn size file** (`max_part_size` chỉ áp dụng cho field text). Đã đo: request 300MB không có token vẫn bị parse hết rồi mới nhận 401 (CPU server 0.32s so với 0.07s khi parse thủ công) | Endpoint nhận `Request`; mọi kiểm tra chạy trước `request.form()` |
| Không giới hạn upload song song / dung lượng | Đầy đĩa (DoS); trong Docker, `/tmp` có thể là tmpfs nằm trên RAM | Semaphore + ngưỡng dung lượng trống + quota user + `TMPDIR` nằm cùng volume với `DOCUMENTS_FOLDER` |
| Không giới hạn chat song song | Burst làm cạn quota Gemini và DB pool | `asyncio.Semaphore` cho mỗi process + mỗi user chỉ 1 stream |

**Upload không phải điểm nghẽn CPU** (benchmark 2026-10-13, FastAPI 0.141 / Starlette 1.6, 1 process, loopback):

| Kịch bản | multipart, chỉ parse | multipart + copy (thiết kế này) | stream raw body (tham khảo) |
|---|---|---|---|
| 20 × 20MB đồng thời | 0.46s CPU | 0.83s CPU | 0.48s CPU |
| 50 × 10MB đồng thời | 0.89s CPU | 1.18s CPU | 0.57s CPU |

Khoảng 1–2.4 giây CPU cho mỗi GB upload. Rủi ro thật của upload là **dung lượng đĩa và I/O**, không phải CPU. Phần nặng CPU là ingest (PyMuPDF, tokenizer), và phần này đã được hàng đợi giới hạn ở `ingest_concurrency`. Multipart phải ghi mỗi file 2 lần (spool → file đích). Chi phí này đã được chấp nhận để giữ upload nhiều file trong một request.

**Mô hình capacity (mỗi process API):**
- Một lượt chat chỉ giữ DB connection ngắn: dense + sparse chạy song song (2 conn), context window (1 conn), lưu message (1 conn). **Trong pha stream LLM không giữ connection nào.**
- `chat_max_concurrency` (mặc định 32) giới hạn số stream đồng thời. Request vượt ngưỡng chờ tối đa `chat_queue_timeout_s`, quá thì trả `503` + `Retry-After`.
- Scale ngang: chạy `uvicorn --workers N` hoặc nhiều replica (limiter tính theo từng process). Ingest: đặt `INGEST_WORKER_ENABLED=false` trên API và chạy K process `scripts/ingest_worker.py`. `SKIP LOCKED` đảm bảo không có hai worker cùng claim một job.
- Trần thực tế là **quota Gemini** (embedding + LLM dùng chung key). Thông số `ingest_concurrency` × số process worker phải nằm trong quota embedding.

### 2.3 Luồng dữ liệu

```
UPLOAD (POST /document/uploadfile)  — các bước 1-5 chạy TRƯỚC khi đọc body
1 auth (get_current_user)                                   → 401
2 Content-Length thiếu / > upload_max_request_mb            → 411 / 413
3 upload_limiter đã đầy (không chờ)                         → 503 + Retry-After
4 disk free(DOCUMENTS_FOLDER) − Content-Length < min_free   → 507
5 user đã chạm quota (bytes hoặc số document)               → 409 quota_exceeded
6 async with request.form(max_files, max_fields=1) as form  (Starlette spool vào TMPDIR)
7 với từng file, tuần tự:
    canonical_document_name(filename), đuôi .pdf, f.size ≤ upload_max_mb
    copy → {uid}/.tmp-{uuid}.pdf  (sha256, magic "%PDF-")
    TX: SELECT users FOR UPDATE (tuần tự hóa theo user để tính quota)
        SELECT documents WHERE user_id, lower(name) FOR UPDATE
        ├─ quota sau khi thêm/thay file bị vượt → "quota_exceeded" (xóa tmp)
        ├─ processing      → "busy" (xóa tmp)
        ├─ hash trùng      → "unchanged" (xóa tmp)
        ├─ không có        → INSERT pending, size_bytes ; os.replace(tmp → {uid}/{name}.pdf) ; COMMIT
        └─ khác            → UPDATE pending, hash, size_bytes, attempts=0 ; os.replace ; COMMIT
8 200 {documents, rejected, usage}

INGEST WORKER (lifespan task hoặc scripts/ingest_worker.py; N slot song song)
loop: claim_next() ── UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING
      ├─ None → sleep(poll_interval)
      └─ job  → attempts > max? → mark_failed
                pipeline.run(job, path) ─► load ─► chunk ─► embed ─► replace chunks ─► mark_indexed
                ├─ DocumentLoadError / FileNotFoundError → mark_failed (lỗi vĩnh viễn)
                ├─ lỗi khác                              → requeue (pending) cho lần thử sau
                └─ CancelledError (shutdown)             → release (pending, attempts-1), raise

CHAT (POST /conversation/{id}/messages, auth, SSE)
validate owner + content ─► docs = indexed ∩ conversation.document_ids (rỗng → 409)
  ─► limiter.acquire(user) (429 nếu user đang có stream; 503 nếu quá tải)
  ─► EventSourceResponse(stream):
       history (3 lượt gần nhất) ─► QueryRewriter (chỉ khi có history) ─► event meta
       RAGService.answer_stream(standalone, SearchScope(uid, docs))
         ContextsEvent → event contexts
         TokenEvent    → event token
         FinalEvent    → lưu user + assistant message (1 TX) → event final
       RAGError → event error ; finally limiter.release
```

### 2.4 API contract

Tất cả mount dưới `/api`, đều cần `Authorization: Bearer <jwt>`, lọc theo `current_user.id`. Tài nguyên của user khác trả về **404** (không lộ sự tồn tại).

**Documents** (`/api/document`)

| Method | Path | Body / Query | Response |
|---|---|---|---|
| `POST` | `/uploadfile` | multipart `files[]` (≤ `upload_max_files`) | `200 {"documents": [DocumentOut], "rejected": [{"filename", "reason"}], "usage": Usage}`. `reason` ∈ `not_pdf`, `too_large`, `empty_name`, `busy`, `unchanged`, `quota_exceeded`. Lỗi của cả request: `400` (quá số file hoặc multipart hỏng), `411` (thiếu `Content-Length`), `413` (vượt `upload_max_request_mb`), `503` + `Retry-After` (hết slot upload), `507` (volume sắp đầy), `409 {"detail": "quota_exceeded"}` (user đã chạm quota) |
| `GET` | `/` | | `200 {"documents": [DocumentOut], "usage": Usage}`, sắp `created_at DESC` |
| `GET` | `/{id}/file` | | `200 application/pdf`, `Content-Disposition: inline; filename="{name}.pdf"`; `404` nếu không có quyền hoặc mất file |
| `POST` | `/{id}/reindex` | | `202 DocumentOut` (đưa về `pending`, `attempts=0`); `409` nếu `processing` |
| `DELETE` | `/{id}` | | `204`; `404`. Xóa row (chunk bị cascade) rồi `unlink(missing_ok=True)` file |

`DocumentOut`: `id, name, title, status, error, size_bytes, num_pages, num_chunks, created_at, indexed_at` (giữ thêm `_id` để tương thích ngược).
`Usage`: `{"bytes": int, "documents": int, "quota_bytes": int, "quota_documents": int}`.

**Conversations** (`/api/conversation`)

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/` | `{"document_ids": [str] (1..10, unique), "title": str?}` | `201 ConversationOut`. `404` nếu có id không thuộc user; `409` nếu có document chưa `indexed` |
| `GET` | `/` | | `200 {"conversations": [ConversationOut]}`, `updated_at DESC`, tối đa 100 |
| `GET` | `/{id}` | | `200 ConversationOut & {"messages": [MessageOut]}` (tối đa 200 tin gần nhất, sắp tăng dần) |
| `DELETE` | `/{id}` | | `204` |
| `POST` | `/{id}/messages` | `{"content": str (1..2000, strip)}` | `text/event-stream` (bên dưới). Trước khi stream: `404`, `409` (không còn tài liệu indexed), `422`, `429`, `503` |

`ConversationOut`: `id, title, documents: [{id, name, title, status}], created_at, updated_at`.
`MessageOut`: `id, role ("user"|"assistant"), content, sources: [Source] | null, grounded, refused, created_at`.
`Source`: `ref, document_id, document_name, document_title, page_start, page_end, section, snippet (≤ 280 ký tự), cited (bool)`.

**SSE events** (field `data` luôn là JSON, kể cả token, để newline không làm vỡ frame):

| event | data |
|---|---|
| `meta` | `{"standalone_query": str}` |
| `contexts` | `{"sources": [Source]}` (lúc này `cited=false`) |
| `token` | `{"text": str}` |
| `final` | `{"message": MessageOut, "timings_ms": {…}}` (assistant message đã lưu, `cited` đã được tính) |
| `error` | `{"detail": str}` (không lưu message nào) |

Comment ping `: ping` của sse-starlette được client bỏ qua.

### 2.5 UI/UX

**Design read:** product workspace có đăng nhập (thư viện tài liệu + RAG chat) cho người đọc paper tiếng Anh. Ngôn ngữ thiết kế tối giản, điềm tĩnh kiểu Linear. Dựa trên shadcn/ui + Tailwind tokens sẵn có, motion chỉ bằng CSS.
**Dials:** `DESIGN_VARIANCE 3 / MOTION_INTENSITY 3 / VISUAL_DENSITY 5`. Đây là product UI chứ không phải landing page, nên chỉ áp dụng các rule về states, contrast, theme/màu/radius lock, reduced-motion, dark mode và copy.

Nguyên tắc chung:
- **Không thêm dependency UI.** Icon giữ `lucide-react` (đã có, một family duy nhất, `strokeWidth` mặc định). Không thêm Motion: `transition-colors`, `motion-safe:animate-pulse` / `motion-safe:animate-spin` là đủ.
- **Chỉ dùng theme token**: bỏ `bg-blue-500`, `bg-gray-200` đang hardcode trong `ChatPage`. Accent duy nhất là `primary`. Radius duy nhất là `--radius` cho input, button, card, bubble. Chip citation dùng `rounded-sm`.
- Dark mode qua `.dark` vars sẵn có; kiểm tra cả hai mode.
- Copy: không em-dash, nhãn ngắn, động từ cụ thể.
- Mọi danh sách đều có đủ trạng thái loading (skeleton theo đúng hình dạng hàng), empty (hướng dẫn hành động tiếp theo) và error (toast cho lỗi tạm thời, inline cho lỗi gắn với một message).

**Documents page** (`/documents`)

```
Documents                                            [ Chat with 2 selected ] [ ⬆ Upload PDF ]
[ 🔍 Search documents…                                        ]
┌──┬──────────────────────────────────┬──────────────┬───────┬────────────┬──────────────────┐
│☐ │ Name                             │ Status       │ Pages │ Uploaded   │                  │
├──┼──────────────────────────────────┼──────────────┼───────┼────────────┼──────────────────┤
│☑ │ attention_is_all_you_need        │ ● Ready · 84 │ 15    │ 2 min ago  │ Chat  Open  🗑    │
│  │ Attention Is All You Need (muted)│              │       │            │                  │
│☐ │ bert                             │ ◌ Processing │ –     │ just now   │ Chat(disabled) 🗑 │
│☐ │ scan_paper                       │ ✕ Failed     │ –     │ 1 h ago    │ Retry  🗑         │
│  │ PDF looks scanned, OCR … (muted destructive, title=full error)                          │
└──┴──────────────────────────────────┴──────────────┴───────┴────────────┴──────────────────┘
```

- Cột status dùng `DocumentStatusBadge` với 4 trạng thái: `Queued` (secondary), `Processing` (outline + `Loader2` `motion-safe:animate-spin`), `Ready` (default, kèm số chunk), `Failed` (destructive). Chấm ● trong mockup chỉ là minh họa; badge chỉ mang text + icon.
- Checkbox native (`<input type="checkbox" class="accent-primary">`), chỉ bật cho document `indexed`. Nút "Chat with N selected" chỉ hiện khi N ≥ 1 (tối đa 10). Nút Chat trên từng hàng là lối tắt cho N = 1.
- Upload: `accept=".pdf,application/pdf"`. Khi đang upload thì nút bị disable và đổi nhãn thành "Uploading…". Kết quả hiện qua toast: "2 queued for processing" và một toast lỗi liệt kê `rejected` với lý do dễ đọc ("not a PDF", "larger than 25 MB", "still processing", "unchanged", "storage quota reached").
  - Lỗi của cả request hiện bằng toast: `413` "Upload is too large, send fewer files at once"; `503` "Too many uploads right now, try again in a few seconds"; `507` "Server storage is full, contact the administrator"; `409` "Storage quota reached, delete documents to free space".
  - Trước khi gửi, client tự lọc file > `upload_max_mb`, file không phải `.pdf`, và quá `upload_max_files`. Đây chỉ là UX; server vẫn kiểm tra lại.
- Usage: dưới tiêu đề "Documents" hiện dòng muted "120 MB of 500 MB used, 12 of 100 documents". Khi vượt 90% quota thì dòng này đổi sang `text-destructive`. Chỉ dùng text, không dùng progress bar.
- Polling: khi có document `pending|processing`, `setInterval` 3s gọi `getDocuments`. Dừng khi `document.hidden` hoặc khi không còn document nào chưa xong; cleanup khi unmount. Khi một document chuyển sang `indexed` hoặc `failed` thì bắn một toast.
- "Uploaded" hiển thị thời gian tương đối bằng `Intl.RelativeTimeFormat` (native), tooltip native `title` là ISO.
- "Open" fetch `/file` có kèm Bearer → `blob` → `URL.createObjectURL` → `window.open`.
- Empty state: "No documents yet" + "Upload a PDF to start asking questions about it." + nút Upload. Loading: 3 hàng skeleton.

**Chat** (`/chat`, `/chat/:conversationId`)

```
┌──────────────────────┬───────────────────────────────────────────────────────────┐
│ [+ New chat]         │ What is multi-head attention?                         🗑   │
│                      │ [attention_is_all_you_need] [bert]                         │
│ ▸ What is multi-head │───────────────────────────────────────────────────────────│
│   2 docs · 3 min     │                           ┌───────────────────────────────┐│
│   How does BERT …    │                           │ What is multi-head attention? ││
│   1 doc · yesterday  │                           └───────────────────────────────┘│
│                      │ Multi-head attention runs several attention functions in   │
│                      │ parallel [1] and concatenates their outputs [1][2].        │
│                      │ Sources                                                    │
│                      │  [1] Attention Is All You Need · p. 4-5 · 3.2.2  Open      │
│                      │  [2] Attention Is All You Need · p. 5          Open       │
│                      │───────────────────────────────────────────────────────────│
│                      │ [ Ask about the selected documents…            ] [Send ⏎] │
└──────────────────────┴───────────────────────────────────────────────────────────┘
```

- Grid `md:grid-cols-[260px_1fr]`. Dưới `md` chỉ hiện một cột: `/chat` hiện danh sách hội thoại, `/chat/:id` hiện thread kèm nút back.
- Cột trái liệt kê hội thoại (title, số tài liệu, thời gian tương đối) và nút **New chat**. Nút này mở `NewChatDialog`: danh sách tài liệu `indexed` có checkbox và ô tìm kiếm, nút "Start chat" bị disable khi chưa chọn tài liệu nào.
- Header của thread: title + chip tên các tài liệu trong scope, kèm nút xóa hội thoại (AlertDialog xác nhận).
- Tin nhắn user: bubble căn phải `bg-primary text-primary-foreground`. Tin nhắn assistant: không có bubble, text `whitespace-pre-wrap leading-relaxed max-w-[70ch]`.
- Citation `[n]` được render thành `<button>` dạng `align-super text-xs rounded-sm bg-muted px-1`. Click thì cuộn tới và highlight dòng source tương ứng (`ring-1 ring-ring`, `transition-colors`).
- **Sources** nằm dưới câu trả lời. Source được trích dẫn hiện đầy đủ, source không được trích dẫn bị ẩn sau nút "Show N more". Mỗi dòng có thể mở rộng để xem `snippet`, nút "Open" mở PDF tại trang đó (`#page=N`).
- Trạng thái stream: trước event `contexts` hiện "Searching documents…", sau đó hiện "Writing answer…" cho tới token đầu tiên. Trong lúc stream, con trỏ `▍` dùng `motion-safe:animate-pulse`. Nút Send đổi thành **Stop**, gọi `AbortController.abort()`.
- `refused`: text muted kèm icon `Info`, không có Sources. Trường hợp `!grounded && !refused`: thêm dòng muted "Some statements could not be matched to a source."
- Lỗi: event `error` hoặc lỗi mạng thì hiện inline dưới message dạng "Couldn't finish this answer." + nút **Retry** (gửi lại cùng câu hỏi). `429` → toast "A reply is already in progress." `503` → toast "Server is busy, try again in a few seconds." `409` → toast "Documents in this chat are no longer available."
- Composer dùng `Textarea` tự giãn tới 6 dòng. Enter để gửi, Shift+Enter xuống dòng, `maxLength=2000`, input bị disable khi đang stream.
- Auto-scroll chỉ chạy khi người dùng đang ở cuối danh sách (cách đáy ≤ 80px) trước khi cập nhật.
- Empty thread: "Ask a question about the selected documents. Answers cite the pages they come from." Loading thread: skeleton 2 bubble.

---

## 3. Implementation

### 3.1 Settings (`app/config.py`, `.env.example`)

```python
# ---- Database pool ----
db_pool_size: int = 10
db_max_overflow: int = 20

# ---- Uploads ----
upload_max_mb: int = 25                 # mỗi file
upload_max_files: int = 10              # mỗi request
upload_max_request_mb: int = 100        # Content-Length tối đa của một request
upload_max_concurrency: int = 8         # request upload đang xử lý mỗi process
upload_min_free_mb: int = 2048          # volume DOCUMENTS_FOLDER còn ít hơn → 507
user_quota_mb: int = 500
user_quota_documents: int = 100

# ---- Ingestion worker ----
ingest_worker_enabled: bool = True     # false khi chạy scripts/ingest_worker.py riêng
ingest_concurrency: int = 2            # job song song mỗi process
ingest_poll_interval_s: float = 2.0
ingest_max_attempts: int = 3
ingest_stale_after_s: int = 900        # job 'processing' quá hạn → được claim lại

# ---- Chat ----
api_reranker: str = "none"             # laya | none (CLI vẫn dùng `reranker`)
chat_max_concurrency: int = 32         # stream đồng thời mỗi process
chat_queue_timeout_s: float = 10.0
chat_history_turns: int = 3            # số lượt (user+assistant) đưa vào rewriter
chat_message_max_chars: int = 2000
conversation_max_documents: int = 10
embedding_query_max_retries: int = 2
query_rewrite_timeout_s: float = 8.0
```

Helper:

```python
def document_file_path(self, user_id: str, name: str) -> Path:
    """name phải là tên đã chuẩn hóa (documents.name). Phòng thủ thêm một lớp:
    path sau khi resolve phải nằm ngay trong thư mục của user."""
    user_dir = (self.documents_folder_path / user_id).resolve()
    path = (user_dir / f"{name}.pdf").resolve()
    if path.parent != user_dir:
        raise ValueError(f"Unsafe document name: {name!r}")
    return path
```

Bỏ `get_document_with_path(filename)` (không còn ai dùng).

**`TMPDIR`** (biến môi trường, không phải setting): Starlette spool file > 1MB vào `tempfile.gettempdir()`. Đặt `TMPDIR` trỏ tới thư mục nằm **cùng volume** với `DOCUMENTS_FOLDER` (ví dụ `documents/.upload-tmp`). Có 3 lý do: check dung lượng trống bao phủ được cả phần spool; không bị dính tmpfs (RAM) trong Docker; và `.tmp` → file đích nằm cùng filesystem. Python đọc `TMPDIR` một lần khi khởi động, nên biến này phải được đặt trong môi trường của process (`.env` của shell/Docker), không đặt được trong `Settings`. Ghi vào `.env.example` và README.

`app/db/session.py`: `create_async_engine(..., pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow, pool_pre_ping=True)`.

### 3.2 Migration `0003_conversations` (`server/alembic/versions/0003_conversations.py`)

```sql
ALTER TABLE documents
  ADD COLUMN attempts   INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN claimed_at TIMESTAMP,
  ADD COLUMN size_bytes BIGINT  NOT NULL DEFAULT 0;

-- unique không phân biệt hoa/thường: macOS (APFS) coi Paper.pdf và paper.pdf
-- là cùng một file, nên DB cũng phải coi đó là cùng một document
CREATE UNIQUE INDEX uq_documents_user_id_lower_name ON documents (user_id, lower(name));

-- index cho câu claim của worker (chỉ chứa job chưa xong → rất nhỏ)
CREATE INDEX ix_documents_queue ON documents (created_at)
  WHERE status IN ('pending', 'processing');

CREATE TABLE conversations (
  id           VARCHAR(36) PRIMARY KEY,
  user_id      VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title        VARCHAR(255),
  document_ids VARCHAR(36)[] NOT NULL,
  created_at   TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at   TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  CONSTRAINT ck_conversations_document_ids
      CHECK (cardinality(document_ids) BETWEEN 1 AND 10)
);
CREATE INDEX ix_conversations_user_id_updated_at
  ON conversations (user_id, updated_at DESC);

CREATE TABLE messages (
  id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  conversation_id  VARCHAR(36) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role             VARCHAR(16) NOT NULL,
  content          TEXT NOT NULL,
  standalone_query TEXT,
  sources          JSONB,
  grounded         BOOLEAN,
  refused          BOOLEAN,
  timings_ms       JSONB,
  created_at       TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  CONSTRAINT ck_messages_role CHECK (role IN ('user', 'assistant'))
);
CREATE INDEX ix_messages_conversation_id_id ON messages (conversation_id, id);
```

- `document_ids` dùng mảng thay vì bảng nối: scope luôn được giao với các document `indexed` của user tại thời điểm chat, nên id đã bị xóa tự rơi ra. Không cần FK.
- Trước khi upgrade trên DB dev, chạy `SELECT user_id, lower(name), count(*) FROM documents GROUP BY 1,2 HAVING count(*) > 1`. Nếu có dòng trùng thì phải xóa tay, nếu không index sẽ fail. Đã kiểm tra ngày 2026-10-13: 0 dòng trùng.
- `lower()` phụ thuộc collation. DB đang dùng `en_US.utf8`, đã kiểm tra `lower('TÀI LIỆU') = 'tài liệu'`. Với collation `C`, `lower()` chỉ hạ chữ ASCII.
- `size_bytes` của các document cũ là 0 (không biết kích thước). Như vậy chúng không bị tính vào quota cho tới khi được upload lại.
- File của document cũ đang nằm phẳng ở `documents/<filename>`. Migration không di chuyển các file này. `GET /{id}/file` trả 404 cho tới khi upload lại; chunk vẫn còn nên chat vẫn hoạt động.
- `downgrade()`: drop bảng, index, constraint và cột theo thứ tự ngược.
- ORM: `app/models/document.py` thêm `attempts`, `claimed_at`, `size_bytes`; `Index("uq_documents_user_id_lower_name", "user_id", func.lower(name), unique=True)`; `Index("ix_documents_queue", "created_at", postgresql_where=...)`. Tạo `app/models/conversation.py` chứa `Conversation` (`ARRAY(String(36))`) và `Message` (`JSONB`). Xóa `app/models/message.py` (enum `MessageSenderType` không còn dùng). Export trong `app/models/__init__.py`.
- `Document.to_dict()` trả thêm `error`, `num_pages`, `indexed_at`.
- `uv run alembic check` phải sạch (index BM25 vẫn được bỏ qua như trước).

### 3.3 Auth và độ an toàn của request

- `app/dependencies.py`: `get_current_user` **không còn phụ thuộc `get_db`**. Nó tự mở `async with AsyncSessionLocal() as s` để tra user rồi đóng ngay. Nhờ vậy route SSE không giữ connection trong suốt stream, bất kể FastAPI dọn dependency `yield` lúc nào.
- Route stream (`POST /conversation/{id}/messages`) **không khai báo `Depends(get_db)`**. Nó đọc và ghi qua các hàm crud mở session ngắn.
- Không còn route nào dưới `/api` (ngoài `auth/*`, `heartbeat/*`) được phép thiếu `get_current_user`. Có test tự động kiểm tra điều này (3.11).

### 3.4 Upload và file storage

**`app/core/storage/naming.py`** (file mới, hàm thuần; dùng chung cho upload, `PgDocumentRepository.get_or_create` và CLI):

```python
_FORBIDDEN = re.compile(r'[/\\:*?"<>|]')

def canonical_document_name(filename: str | None, max_bytes: int = 200) -> str | None:
    """Tên document an toàn để làm tên file trên APFS / ext4.
    1. NFC     : browser trên macOS có thể gửi NFD; APFS coi NFC == NFD.
    2. basename: cắt theo cả '/' và '\\' (Path.name không cắt '\\' trên POSIX).
    3. bỏ đuôi '.pdf' (không phân biệt hoa/thường).
    4. ký tự điều khiển (category C*) và / \\ : * ? " < > |  →  '_'.
    5. gộp whitespace; strip ' ' và '.' ở 2 đầu (không tạo hidden file, không '..').
    6. cắt ≤ max_bytes UTF-8 tại ranh giới ký tự (ext4 giới hạn 255 *byte*; tiếng Việt
       2-3 byte/ký tự), strip lại.
    Rỗng → None."""
```

- Tên ≤ 200 byte cộng `.pdf` vẫn dưới 255 byte. Tiền tố `.tmp-` của file tạm bắt đầu bằng dấu chấm nên không bao giờ trùng với tên đã chuẩn hóa.
- `# ponytail:` `lower()` của Postgres và quy tắc case-folding của APFS khác nhau ở một số ký tự hiếm (`ß`, `İ`). Chấp nhận rủi ro này; nếu gặp thì thêm `casefold()` vào bước chuẩn hóa.
- `PgDocumentRepository.get_or_create(user_id, name)` và `IngestionPipeline.ingest` (CLI) dùng `canonical_document_name(path.name)` và tìm theo `lower(name) = lower(:name)`. Nhờ vậy CLI không vi phạm unique index mới.

**`app/routers/document/limits.py`** (file mới, kiểm tra trước khi đọc body):

```python
class UploadLimiter:
    # ponytail: giới hạn theo từng process; khi chạy nhiều replica thì giới hạn
    # thực tế = N × upload_max_concurrency
    def __init__(self, max_concurrency: int): self._sem = asyncio.Semaphore(max_concurrency)
    @asynccontextmanager
    async def slot(self):
        if self._sem.locked():               # không chờ: trả 503 ngay để client thử lại
            raise HTTPException(503, "Too many uploads", headers={"Retry-After": "5"})
        async with self._sem:                # không có await nào giữa check và acquire → không race
            yield

def check_content_length(request, max_bytes) -> int        # 411 / 413
async def check_disk_free(folder, incoming, min_free) -> None
    # free = (await asyncio.to_thread(shutil.disk_usage, folder)).free
    # free - incoming < min_free → HTTPException(507, "Insufficient storage")
```

`Content-Length` có thể tin làm cận trên: uvicorn chỉ đọc đúng số byte đã khai báo. Browser luôn gửi header này với `FormData`; request dùng `Transfer-Encoding: chunked` (không có header) bị trả 411.

**`app/cruds/document.py`** (viết lại):

```python
CHUNK = 1 << 20

async def usage(db, user_id) -> Usage
    # SELECT coalesce(sum(size_bytes), 0), count(*) FROM documents WHERE user_id = :uid

async def copy_to_tmp(file: UploadFile, user_dir: Path) -> tuple[Path, str, int]:
    """Copy file đã spool → user_dir/.tmp-{uuid}.pdf theo khối 1 MiB, tính sha256.
    5 byte đầu != b"%PDF-" → xóa tmp, raise UploadRejected("not_pdf").
    Thao tác ghi file đi qua asyncio.to_thread; file.read của Starlette đã tự offload."""

async def upsert_upload(db, user, name, tmp, content_hash, size, quota) -> tuple[Document | None, str | None]:
    """1 transaction:
      SELECT 1 FROM users WHERE id = :uid FOR UPDATE      -- tuần tự hóa upload của cùng user
      existing = SELECT … FROM documents
                 WHERE user_id = :uid AND lower(name) = lower(:name) FOR UPDATE
      used     = usage(user)
      new_bytes = used.bytes - (existing.size_bytes if existing else 0) + size
      new_docs  = used.documents + (0 if existing else 1)
      vượt quota_bytes / quota_documents           → (None, "quota_exceeded")
      existing.status == processing                → (None, "busy")
      existing.content_hash == hash, status ∈ {pending, indexed} → (None, "unchanged")
      không có  → INSERT (name, status=pending, content_hash, size_bytes)
      còn lại   → UPDATE status=pending, content_hash, size_bytes, attempts=0,
                  error=NULL, claimed_at=NULL      (giữ nguyên existing.name)
      os.replace(tmp, settings.document_file_path(uid, doc.name)) ; COMMIT → (doc, None)
    os.replace chạy TRƯỚC commit: worker dùng SKIP LOCKED nên không claim được row đang
    bị khóa, và khi đã thấy row thì file trên đĩa chắc chắn là bản mới.
    Mọi nhánh bị reject và mọi exception đều unlink tmp (missing_ok)."""

async def get_owned(db, user, document_id) -> Document | None
async def delete_owned(db, user, document_id) -> bool       # rồi unlink document_file_path(uid, name)
async def requeue_owned(db, user, document_id) -> Document | None   # raise Conflict nếu processing
```

**Endpoint `POST /uploadfile`**: không khai báo tham số body nào. Có test chặn hồi quy (3.11).

```python
@document_router.post("/uploadfile")
async def upload(request: Request, user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    length = check_content_length(request, settings.upload_max_request_mb << 20)
    async with request.app.state.upload_limiter.slot():
        await check_disk_free(settings.documents_folder_path, length, settings.upload_min_free_mb << 20)
        used = await crud.usage(db, user.id)
        if used.bytes >= quota_bytes or used.documents >= quota_documents:
            raise HTTPException(409, "quota_exceeded")       # chặn sớm khi đã đầy hẳn
        async with request.form(max_files=settings.upload_max_files, max_fields=1) as form:
            files = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
            for f in files:   # tuần tự
                name = canonical_document_name(f.filename)
                # name None → empty_name ; filename không đuôi .pdf → not_pdf ;
                # f.size > upload_max_mb → too_large (size đã biết sau khi parse)
                tmp, h, size = await crud.copy_to_tmp(f, user_dir)
                doc, reason = await crud.upsert_upload(db, user, name, tmp, h, size, quota)
    return {"documents": [...], "rejected": [...], "usage": await crud.usage(db, user.id)}
```

- `MultiPartException` (quá `max_files`, multipart hỏng) được Starlette chuyển thành `400`.
- `async with request.form(...)` đóng và xóa các file spool ngay khi xử lý xong, không phải chờ request kết thúc.
- Thư mục `{uid}/` được tạo bằng `mkdir(parents=True, exist_ok=True)` qua `to_thread`.
- Chặn sớm theo quota là ước lượng (chỉ chặn khi user đã đầy hẳn). Kiểm tra chính xác nằm trong transaction của `upsert_upload`, vì upload lại một tên đã có chỉ làm thay đổi phần chênh lệch kích thước.
- Lượng dữ liệu lớn nhất có thể bị spool là `upload_max_concurrency × upload_max_request_mb` = 800MB mỗi process. Con số này nhỏ hơn nhiều so với `upload_min_free_mb`.
- Reverse proxy vẫn nên đặt `client_max_body_size ≥ upload_max_request_mb` để chặn sớm ở tầng mạng. Ghi điều này trong README.

### 3.5 Ingestion queue và worker

**`core/interfaces.py`**: mở rộng `DocumentStore`:

```python
async def claim_next(self, *, stale_after_s: int) -> DocumentRecord | None: ...
async def requeue(self, document_id: str, error: str) -> None: ...
async def release(self, document_id: str) -> None: ...   # shutdown: pending, attempts-1
```

`DocumentRecord` thêm `attempts: int = 0`.

**`core/storage/document_repository.py`**: thêm 3 method trên.

```sql
-- claim_next
UPDATE documents
SET status = 'processing', attempts = attempts + 1,
    claimed_at = (now() AT TIME ZONE 'utc'), error = NULL
WHERE id = (
  SELECT id FROM documents
  WHERE status = 'pending'
     OR (status = 'processing'
         AND claimed_at < (now() AT TIME ZONE 'utc') - make_interval(secs => :stale))
  ORDER BY created_at
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
RETURNING id, user_id, name, title, status, content_hash, num_chunks, attempts;
```

- `requeue`: `status='pending', error=:error, claimed_at=NULL`.
- `release`: `status='pending', attempts=GREATEST(attempts-1, 0), claimed_at=NULL WHERE status='processing'`.
- Cột `TIMESTAMP` không có tz và app dùng `utcnow()`, nên SQL phải luôn dùng `now() AT TIME ZONE 'utc'`.

**`core/ingestion/pipeline.py`**: tách logic chạy job khỏi logic quản lý trạng thái:

```python
async def run(self, doc: DocumentRecord, path: Path) -> IngestReport:
    """load → chunk → embed → replace_document_chunks → mark_indexed.
    KHÔNG gọi mark_processing / mark_failed (caller lo phần đó)."""

async def ingest(self, path, user_id, *, force=False) -> IngestReport:
    """Hành vi CLI giữ nguyên: hash → get_or_create → skip → mark_processing →
    try: run() except: mark_failed; raise."""
```

`content_hash` của `mark_indexed` lấy từ `doc.content_hash` (đã có từ lúc upload). Riêng CLI thì tính từ file.

**`core/ingestion/worker.py`** (file mới, chỉ phụ thuộc Protocol và stdlib):

```python
PERMANENT = (DocumentLoadError, FileNotFoundError)

class IngestionWorker:
    def __init__(self, pipeline, documents: DocumentStore,
                 resolve_path: Callable[[DocumentRecord], Path], *,
                 concurrency=2, poll_interval_s=2.0, max_attempts=3, stale_after_s=900): ...

    async def run_forever(self) -> None:
        # ponytail: poll mỗi poll_interval_s; LISTEN/NOTIFY nếu cần độ trễ < 1s
        sem = asyncio.Semaphore(self.concurrency)
        async with asyncio.TaskGroup() as tg:
            while True:
                await sem.acquire()
                try:
                    job = await self.documents.claim_next(stale_after_s=...)
                except Exception:
                    logger.exception("claim failed"); sem.release()
                    await asyncio.sleep(self.poll_interval_s); continue
                if job is None:
                    sem.release(); await asyncio.sleep(self.poll_interval_s); continue
                tg.create_task(self._process(job, sem))

    async def _process(self, job, sem) -> None:
        try:
            if job.attempts > self.max_attempts:
                await self.documents.mark_failed(job.id, f"Gave up after {self.max_attempts} attempts")
                return
            await self.pipeline.run(job, self.resolve_path(job))
        except asyncio.CancelledError:
            await asyncio.shield(self.documents.release(job.id)); raise
        except PERMANENT as e:
            await self.documents.mark_failed(job.id, f"{type(e).__name__}: {e}")
        except Exception as e:
            logger.exception("ingest {} failed (attempt {})", job.id, job.attempts)
            await self.documents.requeue(job.id, f"{type(e).__name__}: {e}")
        finally:
            sem.release()
```

- `_process` không bao giờ raise ra ngoài (trừ `CancelledError`), nên `TaskGroup` không bị hủy chỉ vì một job lỗi.
- Không có backoff giữa các lần requeue: embedder đã retry exponential bên trong (tới 6 lần), và job dừng sau `max_attempts`.
- Job bị xóa giữa chừng sẽ gây FK error khi insert chunk → `requeue` không cập nhật được row nào. Chỉ cần log, không cần xử lý gì thêm.
- `# ponytail:` job chạy lâu hơn `ingest_stale_after_s` có thể bị claim lần nữa. Nếu có PDF lớn hơn mức đó thì tăng giá trị này.

**Chạy worker:**
- `app/main.py` lifespan: tạo `app.state.upload_limiter = UploadLimiter(settings.upload_max_concurrency)`. Nếu `settings.ingest_worker_enabled` thì `task = asyncio.create_task(build_ingest_worker().run_forever())`. Khi shutdown thì `task.cancel()` rồi `await` (bỏ qua `CancelledError`). Nhờ vậy job đang dở được `release` về `pending`, kể cả khi uvicorn `--reload` restart.
- `scripts/ingest_worker.py`: theo idiom `SERVER_DIR` của `seed.py`. `asyncio.run(build_ingest_worker().run_forever())`, bắt `KeyboardInterrupt`.

### 3.6 LLM và core (`core/llm/gemini_provider.py`, `core/factory.py`)

**`GeminiProvider`**
- `__init__` nhận thêm `client: genai.Client | None = None` (factory truyền client dùng chung).
- `_generate_stream` viết lại; xóa `_run_stream_in_thread` và `import threading`:

```python
async def _generate_stream(self, query, system_instruction):
    try:
        stream = await self.client.aio.models.generate_content_stream(
            model=self.model_name,
            contents=self._build_contents(query),
            config=self._build_config(system_instruction),
        )
        async for chunk in stream:
            if chunk.text:
                yield ServerSentEvent(data=chunk.text, event="message")
    except Exception as e:  # CancelledError là BaseException → vẫn propagate
        yield ServerSentEvent(data=f"[Error] Gemini streaming failed: {e}", event="error")
```

Contract `message`/`error` không đổi, nên `AnswerGenerator.stream` và CLI không phải sửa.

**`core/generation/query_rewriter.py`** (file mới):

```python
REWRITE_SYSTEM_PROMPT = """Rewrite the user's follow-up question into a standalone question \
that can be understood without the conversation. Keep the original language and keep \
technical terms verbatim. If it is already standalone, return it unchanged. \
Output only the question."""

class QueryRewriter:
    def __init__(self, llm: LLMBase, timeout_s: float = 8.0, max_chars: int = 500): ...

    async def rewrite(self, question: str, history: Sequence[tuple[str, str]]) -> str:
        """history = [(role, content)…] theo thứ tự thời gian.
        - history rỗng → trả question, KHÔNG gọi LLM.
        - Bỏ citation [n] khỏi câu trả lời assistant trước khi đưa vào prompt.
        - Gọi llm.generate(stream=False) với asyncio.wait_for(timeout).
        - Lỗi / timeout / kết quả rỗng / dài hơn max_chars → log warning, trả question gốc.
        - Bỏ dấu nháy và tiền tố kiểu 'Question:' ở đầu/cuối."""
```

**`core/factory.py`**
- Thêm tham số `max_retries: int | None = None` cho `build_embedder(s, max_retries=None)` (mặc định `s.embedding_max_retries`). Thêm tham số `embedder: Embedder | None = None` cho `build_retriever(mode, s, *, embedder=None)`.
- `build_rag_service(..., query_max_retries: int | None = None)`: truyền embedder phía query có số lần retry riêng. `GeminiProvider(s.gemini_model, client=_genai_client(s.gemini_api_key))`.
- `build_query_rewriter(s) -> QueryRewriter`.
- `build_ingest_worker(s) -> IngestionWorker`: `resolve_path=lambda d: s.document_file_path(d.user_id, d.name)`.
- `build_api_services(s) -> ApiServices` (dataclass gồm `rag`, `rewriter`) được gọi **một lần** trong lifespan và lưu ở `app.state.services`. Không build lại cho mỗi request. Toàn bộ object đều stateless, chỉ giữ session factory hoặc client.

### 3.7 Conversation layer

**`app/schemas/document.py`, `app/schemas/conversation.py`**: Pydantic v2 cho `DocumentOut`, `UploadResult`, `ConversationCreate` (`document_ids: list[str] = Field(min_length=1, max_length=10)`, validator bỏ trùng, `title: str | None = Field(None, max_length=255)`), `ConversationOut`, `MessageCreate` (`content: str`, strip, `1..chat_message_max_chars`), `MessageOut`, `Source`. Xóa `schemas/message.py`, và xóa `schemas/conversation.py` rỗng hiện tại trước khi tạo lại.

**`app/cruds/conversation.py`** (mọi hàm nhận `session_factory` hoặc `db`, tất cả đều lọc theo `user_id`):

```python
async def create(db, user, document_ids, title) -> Conversation      # 404/409 theo 2.4
async def list_for_user(db, user, limit=100) -> list[tuple[Conversation, list[Document]]]
async def get_owned(db, user, conversation_id) -> Conversation | None
async def get_messages(db, conversation_id, limit=200) -> list[Message]
async def delete_owned(db, user, conversation_id) -> bool
async def indexed_scope(sf, user_id, document_ids) -> tuple[str, ...]  # giao với status='indexed'
async def recent_history(sf, conversation_id, turns) -> list[tuple[str, str]]
async def save_turn(sf, conversation_id, user_text, answer: Answer, standalone, sources) -> Message
    # 1 TX: INSERT user + assistant; UPDATE conversations SET updated_at=now,
    #       title = COALESCE(title, left(user_text, 80))
```

`list_for_user` lấy tên các document bằng **một** query `WHERE id = ANY(:all_ids) AND user_id = :uid`. Không để xảy ra N+1.

**`app/routers/conversation/limiter.py`**:

```python
class ChatLimiter:
    # ponytail: giới hạn theo từng process; khi chạy nhiều replica thì giới hạn
    # thực tế = N × chat_max_concurrency. Cần giới hạn toàn cục thì dùng Redis.
    def __init__(self, max_concurrency: int, timeout_s: float): ...
    async def acquire(self, user_id: str) -> None:
        # user_id đang có stream → HTTPException(429)
        # chờ semaphore quá timeout → HTTPException(503, headers={"Retry-After": "5"})
    def release(self, user_id: str) -> None
```

Đặt `app.state.chat_limiter` trong lifespan.

**`app/routers/conversation/services.py`** (viết lại, xóa `ChatStreamService`):

```python
def to_sources(contexts, cited_refs: set[int]) -> list[dict]   # snippet = text[:280]

async def stream_reply(*, services, user_id, conversation_id, content,
                       scope_ids, history, release) -> AsyncIterator[ServerSentEvent]:
    try:
        standalone = await services.rewriter.rewrite(content, history)
        yield sse("meta", {"standalone_query": standalone})
        scope = SearchScope(user_id=user_id, document_ids=scope_ids)   # scope_ids KHÔNG rỗng
        async for ev in services.rag.answer_stream(standalone, scope):
            if isinstance(ev, ContextsEvent):  yield sse("contexts", {"sources": to_sources(ev.contexts, set())})
            elif isinstance(ev, TokenEvent):   yield sse("token", {"text": ev.text})
            else:
                a = ev.answer
                msg = await crud.save_turn(..., content, a, standalone,
                                           to_sources(a.contexts, {c.ref for c in a.citations}))
                yield sse("final", {"message": MessageOut…, "timings_ms": a.timings_ms})
    except RAGError as e:
        yield sse("error", {"detail": str(e)})
    except Exception:
        logger.exception("chat stream failed"); yield sse("error", {"detail": "Internal error"})
    finally:
        release()
```

`sse(event, data)` = `ServerSentEvent(event=event, data=json.dumps(data, ensure_ascii=False))`.

**`app/routers/conversation/endpoint.py`**: các route theo bảng 2.4. Route messages:

```python
@conversation_router.post("/{conversation_id}/messages")
async def post_message(conversation_id: str, body: MessageCreate, request: Request,
                       user: User = Depends(get_current_user)):
    conv = await crud.get_owned_sf(AsyncSessionLocal, user, conversation_id)  # 404
    scope_ids = await crud.indexed_scope(AsyncSessionLocal, user.id, conv.document_ids)
    if not scope_ids: raise HTTPException(409, "Documents in this chat are no longer available")
    history = await crud.recent_history(AsyncSessionLocal, conv.id, settings.chat_history_turns)
    limiter = request.app.state.chat_limiter
    await limiter.acquire(user.id)                # 429 / 503 trước khi mở stream
    return EventSourceResponse(stream_reply(..., release=lambda: limiter.release(user.id)))
```

- Bất biến mới: **`SearchScope.document_ids` của API không bao giờ là tuple rỗng**. Tuple rỗng đồng nghĩa với "toàn bộ tài liệu của user" (xem `retrieval/dense.py:39`). Endpoint trả 409 trước khi tới được dòng đó.
- Client ngắt kết nối → sse-starlette hủy task → `CancelledError` lan qua `answer_stream` và stream aio của Gemini (hủy được request HTTP) → `finally` release limiter. Không lưu message nào.

**`app/routers/document/endpoint.py`**: các route theo 2.4. `GET /{id}/file` dùng `FileResponse(settings.document_file_path(uid, doc.name), media_type="application/pdf", filename=f"{doc.name}.pdf", content_disposition_type="inline")`. Starlette tự encode tên Unicode theo RFC 5987 (`filename*=utf-8''…`).

### 3.8 Client: API layer

- **`api/config.ts`** thêm:
  - `apiDocumentFile(id)`, `apiReindexDocument(id)`
  - `apiConversations`, `apiConversation(id)`, `apiConversationMessages(id)`
- **`api/apiClient.ts`**:
  - Tách `buildHeaders(options)` để dùng chung.
  - Khi response `401` và `auth=true`: gọi `authService.logout()` rồi `window.location.assign("/login")`.
  - Thêm `apiFetchBlob(path)` (dùng cho Open PDF).
  - Thêm `apiStream`:

```ts
export async function apiStream(path: string, opts: {
  json: unknown; signal?: AbortSignal;
  onEvent: (event: string, data: unknown) => void;
}): Promise<void>
// fetch POST + Bearer; !ok → ApiError(status, body)
// response.body.pipeThrough(new TextDecoderStream()); buffer; tách frame bằng /\r?\n\r?\n/
// mỗi frame: bỏ dòng bắt đầu bằng ":" (ping); "event:" → tên; "data:" → nối bằng "\n"; JSON.parse
```

- **`api/types/document.ts`**:
  - `Document { id; name; title: string | null; status: DocumentStatus; error: string | null; size_bytes: number; num_pages: number | null; num_chunks: number; created_at: string; indexed_at: string | null }`
  - `Usage { bytes; documents; quota_bytes; quota_documents }`
  - `DocumentsResponse { documents: Document[]; usage: Usage }`
  - `UploadResponse { documents: Document[]; rejected: { filename: string; reason: RejectReason }[]; usage: Usage }`
- **`api/types/conversation.ts`**: `Conversation`, `ConversationDetail`, `Message`, `Source`, và union kiểu `ChatEvent`.
- **`api/services/document.service.ts`**:
  - `deleteDocument` trả về `void` (204).
  - Thêm `reindex(id)` và `openFile(id, page?)` (blob → object URL → `window.open(url + (page ? #page=N : ""))`, rồi `revokeObjectURL` sau 60s).
- **`api/services/conversation.service.ts`**: `list`, `get`, `create`, `remove`, `sendMessage(id, content, {signal, onEvent})`.

### 3.9 Client: UI

**Thêm vào `components/ui`** (code shadcn chuẩn, không thêm dependency): `badge.tsx`, `textarea.tsx`, `skeleton.tsx`, `dialog.tsx` (dùng `@radix-ui/react-dialog` đã có sẵn).

**`components/documents/DocumentStatusBadge.tsx`**: map 4 status sang variant/icon/label như 2.5.

**`pages/DocumentsPage.tsx`**: viết lại theo 2.5.
- State: `documents`, `loading`, `uploading`, `selected: Set<string>`, `search`.
- Polling `useEffect`: phụ thuộc vào `hasActive = documents.some(d => d.status === "pending" || d.status === "processing")`. So sánh với snapshot trước đó để bắn toast khi status chuyển.
- "Chat with selected" gọi `conversationService.create({document_ids})` rồi `navigate(`/chat/${id}`)`.
- Sửa các lỗi sẵn có: `colSpan` đúng số cột, bỏ biến `isMounted` không dùng, dùng `doc.id`.

**`hooks/useChatStream.ts`**: state machine cho một lượt chat.

```ts
type Phase = "idle" | "searching" | "writing" | "error";
// send(content): thêm message user tạm + assistant "draft"; AbortController;
//   meta → (bỏ qua, chỉ log debug) ; contexts → draft.sources, phase "writing";
//   token → draft.content += text ; final → thay draft bằng message đã lưu ; error → phase "error"
// stop(): abort → giữ phần text đã nhận, đánh dấu "stopped" (chỉ ở client, server không lưu)
// retry(): gửi lại content cuối
```

**`components/chat/`**:
- `ConversationList.tsx`: danh sách + New chat, highlight hội thoại đang mở; skeleton/empty.
- `NewChatDialog.tsx`: tải `getDocuments`, chỉ hiện document `indexed`, có checkbox và ô tìm kiếm, tối đa 10.
- `AssistantMessage.tsx`: tách text theo `/\[(\d+)\]/` → chip citation; Sources (cited trước, phần còn lại trong "Show N more"); refused/ungrounded/error/streaming caret.

**`pages/ChatPage.tsx`**:
- `useParams<{conversationId}>`; `/chat` không có id thì hiện list và empty state "Pick a conversation or start a new one".
- Có id: `conversationService.get` → header + messages + composer (`Textarea`, Enter/Shift+Enter).
- Sau `final` thì cập nhật title trong list (refetch list, chi phí thấp).
- Xóa toàn bộ mock `setTimeout`.

**`router.tsx`**: `/chat/:documentId` → `/chat/:conversationId`. **`Layout.tsx`**: nav "New Chat" → "Chats" (`/chat`); active khi `pathname.startsWith(item.to)`.

### 3.10 Docs

- `docs/architecture.md`:
  - Storage model: thêm `conversations`, `messages`, file theo `{user_id}/{name}.pdf` (tên đã chuẩn hóa), cột queue, `size_bytes` + quota.
  - Auth: xóa mục "Gaps".
  - Thêm invariant: scope rỗng bị cấm ở API; ingest qua Postgres queue; giới hạn chat theo process; LLM stream dùng SDK async.
- `docs/code-standards.md`: route stream không dùng `get_db`; SSE `data` là JSON.
- `docs/progress-tracker.md`: cập nhật Completed/Next/Open Questions.
- `README.md`: cập nhật bảng endpoint, cách chạy `scripts/ingest_worker.py`, ghi chú `client_max_body_size`.

### 3.11 Tests

Không cần DB/API thật; dùng fake theo kiểu `tests/core/conftest.py`.

- `tests/core/test_ingest_worker.py` (fake `DocumentStore` + fake pipeline):
  - Không bao giờ có quá `concurrency` job chạy cùng lúc.
  - `DocumentLoadError` → `mark_failed` ngay, không requeue.
  - Lỗi tạm thời → `requeue`; `attempts > max` → `mark_failed`.
  - Hủy task giữa job → `release` được gọi.
  - Lỗi khi claim không làm chết vòng lặp.
- `tests/core/test_query_rewriter.py`:
  - History rỗng thì không gọi LLM.
  - LLM raise hoặc timeout → trả về câu gốc.
  - Bỏ `[n]` khỏi history và bỏ tiền tố `Question:`.
- `tests/api/test_auth_required.py`: duyệt `app.routes`; với mọi `APIRoute` dưới `/api` (trừ `/api/auth`, `/api/heartbeat`), gọi qua `httpx.ASGITransport` (không chạy lifespan, không cần DB) mà không có token → `401`.
- `tests/core/test_naming.py` (`canonical_document_name`):
  - `"../../etc/passwd.pdf"` → `"passwd"`; `"..\\..\\x.PDF"` → `"x"`.
  - NFD và NFC cho ra cùng kết quả; `'a:b*c?.pdf'` → `"a_b_c_"`; ký tự `\x00` / `\n` → `_`.
  - `".pdf"`, `" . .pdf"`, `""`, `None` → `None`; whitespace bị gộp.
  - Tên tiếng Việt 300 ký tự → ≤ 200 byte, decode được, không bị cắt giữa ký tự.
- `tests/api/test_upload_route.py`:
  - Route `POST /api/document/uploadfile` có `route.body_field is None` (chặn hồi quy: nếu ai đó khai báo lại `UploadFile` thì FastAPI sẽ parse body trước auth).
  - Không có token → 401; thiếu `Content-Length` → 411; vượt quá → 413 (gọi qua `ASGITransport`, không cần DB).
- `tests/api/test_upload_helpers.py`: `copy_to_tmp` từ chối file không phải PDF và dọn file tmp; `UploadLimiter` trả 503 khi đầy và nhả slot khi xong.
- `tests/api/test_sse_parse.py`: **không làm**. Parser phía client được kiểm thử thủ công qua checklist.

**Load check**: `server/scripts/load_chat.py` (httpx, đã có trong dev deps). Script nhận `--users N --questions Q --conversation ID --token T`, chạy N stream song song rồi in TTFT p50/p95, tổng thời gian p50/p95 và đếm `429/503/error`.

---

## 4. Dependencies

**Không thêm dependency mới** cho cả server lẫn client.

- Server: dùng lại `sse-starlette`, `google-genai` (`aio.models.generate_content_stream`), SQLAlchemy `ARRAY`/`JSONB`, `httpx` (dev, cho test + load script).
- Client:
  - `@radix-ui/react-dialog` (đã có) cho `dialog.tsx`.
  - Checkbox native, `Intl.RelativeTimeFormat`, `TextDecoderStream` và `AbortController` đều là API native.
  - Không thêm markdown renderer: câu trả lời render bằng `whitespace-pre-wrap`. Thêm `react-markdown` khi cần list/bảng thật.
- Hạ tầng: không đổi (vẫn ParadeDB image). Khi deploy sau reverse proxy thì đặt `client_max_body_size ≥ upload_max_mb` và tắt buffering cho `text/event-stream`.

---

## 5. Verification checklist

**Migration**
- [ ] `uv run alembic upgrade head` → có `conversations`, `messages`, `documents.attempts`, `claimed_at`, `size_bytes`, `uq_documents_user_id_lower_name`, `ix_documents_queue`.
- [ ] `alembic downgrade 0002_rag_core && alembic upgrade head` không lỗi; `uv run alembic check` sạch.

**Auth**
- [ ] `pytest tests/api/test_auth_required.py` pass.
- [ ] Endpoint `POST /api/conversation/stream` không còn tồn tại (404).
- [ ] User B dùng token của mình gọi `GET /document/{id_của_A}/file`, `DELETE`, `reindex`, `GET /conversation/{id_của_A}` → tất cả trả `404`.

**Upload và ingest**
- [ ] Upload 3 PDF → `200`, status `pending` → trong vòng vài giây chuyển `processing` → `indexed`, `num_chunks > 0`. File nằm ở `documents/{uid}/{name}.pdf`.
- [ ] Upload `.txt` đổi đuôi thành `.pdf` → `rejected: not_pdf`. Upload file > 25 MB → `too_large`. Upload 11 file → `400`. Gửi request > 100 MB → `413`; `curl -H "Transfer-Encoding: chunked"` → `411`.
- [ ] Upload **không có token** kèm 300 MB → `401`, và thư mục `TMPDIR` không xuất hiện file spool nào (theo dõi bằng `ls` trong lúc gửi).
- [ ] Upload `Paper.pdf` rồi `paper.pdf` (nội dung khác) → cùng 1 document được ingest lại, giữ tên `Paper`, chỉ có 1 file trên đĩa.
- [ ] Upload `Tài liệu.pdf` dạng NFD (`python -c "import unicodedata;print(unicodedata.normalize('NFD','Tài liệu.pdf'))"`) rồi dạng NFC → cùng 1 document.
- [ ] Tên tiếng Việt dài 300 ký tự → `name` ≤ 200 byte và file tạo được (test trên Docker/Linux ext4).
- [ ] `upload_max_concurrency=1`: gửi 2 upload lớn song song → một request nhận `503` kèm `Retry-After`.
- [ ] `upload_min_free_mb` lớn hơn dung lượng trống hiện tại → `507`, không file nào được ghi.
- [ ] `user_quota_documents=2`: upload 3 file → 2 file được nhận, file thứ ba bị `quota_exceeded`. Upload lại 1 file đã có (nội dung khác) vẫn thành công. Khi đã đầy, request tiếp theo nhận `409` ngay trước khi body bị parse.
- [ ] 2 tab cùng upload sát quota → tổng `size_bytes` không vượt quota (khóa row user tuần tự hóa các upload).
- [ ] Upload lại cùng file → `unchanged`. Sửa file rồi upload lại → `pending` → `indexed`, số chunk mới, không có dòng trùng.
- [ ] Upload lại trong lúc `processing` → `busy`.
- [ ] Filename `../../x.pdf` và `..\\..\\x.pdf` → lưu đúng `{uid}/x.pdf`, `name == "x"`; filename `.pdf` hoặc `...pdf` → `empty_name`.
- [ ] PDF scan → `failed` sau **1** lần thử, có `error`, client hiện Retry. Bấm Retry → `pending`.
- [ ] Kill server khi đang `processing` (Ctrl+C) → document về lại `pending`, và được ingest tiếp khi khởi động lại.
- [ ] `kill -9` khi đang `processing` → sau `ingest_stale_after_s` (test với giá trị 30s) document được claim lại.
- [ ] `INGEST_WORKER_ENABLED=false` + chạy 2 process `scripts/ingest_worker.py`, upload 6 file → mỗi document được ingest đúng 1 lần (log không có id nào bị claim 2 lần), tổng số job song song ≤ 2×`ingest_concurrency`.
- [ ] Xóa document → `204`, file trên đĩa bị xóa, chunk bị cascade.

**Conversation**
- [ ] Tạo conversation với 2 document indexed → `201`. Dùng document `pending` → `409`. Dùng id của user khác → `404`. Dùng 11 id → `422`.
- [ ] Gửi câu hỏi → các event theo đúng thứ tự `meta → contexts → token… → final`. `final.message.sources` có `cited=true` khớp với các `[n]` trong text. Reload trang thì thấy cả 2 message.
- [ ] Câu follow-up ("what about its complexity?") → `meta.standalone_query` là câu độc lập. Câu đầu tiên của hội thoại không gọi rewriter (log cho thấy không có LLM call).
- [ ] Câu ngoài tài liệu → `refused=true`, không có sources, `timings_ms` không có `llm`.
- [ ] Retrieval chỉ trả chunk thuộc `document_ids` của hội thoại. Xóa hết document của hội thoại → gửi message bị `409`.
- [ ] Đặt API key sai → event `error`, không có message nào được lưu.
- [ ] Gửi 2 message song song cùng user → request thứ hai nhận `429`.
- [ ] Đóng tab giữa lúc stream → log cho thấy stream bị hủy, limiter được release (user đó gửi lại được ngay), không có message nào được lưu.
- [ ] Trong lúc stream, `SELECT count(*) FROM pg_stat_activity WHERE datname='docmind' AND state <> 'idle'` không tăng theo số stream đang mở.

**Tải**
- [ ] `load_chat.py --users 20` (20 user khác nhau) với `api_reranker=none`: không có lỗi 5xx ngoài 503 có chủ đích. Ghi TTFT p50/p95 vào spec này.
- [ ] `chat_max_concurrency=4` + 10 user → một phần request nhận `503` kèm `Retry-After`, server không treo.
- [ ] Upload 10 file trong lúc 10 user đang chat → TTFT của chat không tăng quá 2× so với baseline.

**Client**
- [ ] Documents: skeleton khi đang load; empty state; badge cập nhật qua polling mà không phải reload; polling dừng khi mọi document đã xong; có toast khi xong hoặc lỗi; Open mở được PDF; nút Chat bị disable khi document chưa indexed.
- [ ] Chọn nhiều document → Chat with selected → mở hội thoại mới, header hiện đủ chip.
- [ ] Chat: các trạng thái "Searching documents…" → "Writing answer…" → token chạy ra; Stop dừng được; citation click thì highlight source; Open trên source mở đúng trang PDF; Retry sau lỗi hoạt động.
- [ ] Token hết hạn → mọi request `401` đều đưa về `/login`.
- [ ] Kiểm tra light + dark mode; mobile < 768px (list ↔ thread); `prefers-reduced-motion` thì không còn spin/pulse; không có màu hardcode (`git grep -n "bg-blue-\|bg-gray-" client/src` không có kết quả); không có em-dash trong copy UI.
- [ ] `npm run build` và `npm run lint` pass.

**Chất lượng**
- [ ] `uv run pytest -v` pass toàn bộ (core + api).
- [ ] `make quality` pass.
- [ ] `docs/architecture.md`, `docs/progress-tracker.md` và `README.md` đã được cập nhật.

---

## 6. Ngoài phạm vi / để sau

- Upload dạng raw stream (1 file/request) để chỉ ghi một lần (benchmark 2.2: tiết kiệm ~40% CPU so với multipart + copy), hoặc presigned URL lên S3/MinIO khi scale nhiều replica.
- Đổi tên document (phải đổi tên cả file trên đĩa).
- Dịch câu hỏi tiếng Việt sang tiếng Anh cho BM25. Có thể gộp vào prompt của `QueryRewriter` sau này, vì đằng nào cũng đã có một lượt gọi LLM.
- Rate limit toàn cục (Redis) giữa các replica; `LISTEN/NOTIFY` để giảm độ trễ claim job.
- Đổi tên hội thoại, phân trang danh sách hội thoại và message (hiện giới hạn 100/200).
- Render markdown cho câu trả lời; xem PDF ngay trong app (hiện mở bằng tab mới).
- Reranker cho deploy Linux (cross-encoder). Hiện API mặc định dùng `none`.
- Chia sẻ tài liệu giữa nhiều user.
