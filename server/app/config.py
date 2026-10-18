import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parents[2]
ENV_PATHS = (
    os.path.join(os.getcwd(), ".env"),
    str(SERVER_DIR / ".env"),
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATHS,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Project Information -----
    name: str = "Doc-Mind"
    version: str = "0.1.0"
    description: str = "Doc-Mind API Server"
    author: str = "Doc-Mind Team"
    debug: bool = True

    # ---- Server configure ----
    host: str = "0.0.0.0"
    port: int = 8000

    # ---- Secret Token ----
    jwt_secret_key: str = "your-super-secret-jwt-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440

    # ---- Database configure (PostgreSQL) ----
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "docmind"

    # ---- Default Admin Seed ----
    first_superuser: str = "admin"
    first_superuser_password: str = "Admin@123456"

    # ---- Documents folder ----
    documents_folder: str = "./documents"

    # ---- Gemini (embedding) ----
    gemini_api_key: str = ""

    # ---- LLM (endpoint tương thích OpenAI: Gemini, vLLM, OpenRouter...) ----
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: str = ""
    llm_model: str = "gemini-3.5-flash-lite"
    llm_reasoning_effort: str = "minimal"  # rỗng = không gửi (vd. vLLM)

    # ---- Embedding ----
    embedding_model: str = "gemini-embedding-2"
    embedding_dim: int = 768  # phải khớp vector(768) trong migration
    embedding_batch_size: int = 32  # hard limit API = 100
    embedding_max_retries: int = 6
    embedding_query_task: str = "question answering"  # hoặc "search result"

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
    retrieval_candidates: int = 30  # số candidate xét ngưỡng dense trước khi cắt top_n
    retrieval_top_n: int = 5  # số chunk đưa vào context
    hnsw_ef_search: int = 100
    retrieval_min_dense_score: float = 0.65

    # ---- Generation ----
    context_window: int = 0  # số chunk liền kề mỗi phía (small-to-big)
    context_max_tokens: int = 6000

    # ---- Database pool ----
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ---- Uploads ----
    upload_max_mb: int = 25  # mỗi file
    upload_max_files: int = 10  # mỗi request
    upload_max_request_mb: int = 100  # Content-Length tối đa của một request
    upload_max_concurrency: int = 8  # request upload đang xử lý mỗi process
    upload_min_free_mb: int = 2048  # volume DOCUMENTS_FOLDER còn ít hơn → 507
    user_quota_mb: int = 500
    user_quota_documents: int = 100

    # ---- Ingestion worker ----
    ingest_worker_enabled: bool = True  # false khi chạy scripts/ingest_worker.py
    ingest_concurrency: int = 2  # job song song mỗi process
    ingest_poll_interval_s: float = 2.0
    ingest_max_attempts: int = 3
    ingest_stale_after_s: int = 900  # job 'processing' quá hạn → claim lại

    # ---- Chat ----
    chat_max_concurrency: int = 32  # stream đồng thời mỗi process
    chat_queue_timeout_s: float = 10.0
    chat_history_turns: int = 3  # số lượt (user+assistant) đưa vào rewriter
    chat_message_max_chars: int = 2000
    conversation_max_documents: int = 10
    embedding_query_max_retries: int = 2
    query_rewrite_timeout_s: float = 8.0

    # Helper database configure ----
    @property
    def db_uri(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_db_uri(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Helper Documents folder ----
    @property
    def documents_folder_path(self) -> Path:
        return Path(self.documents_folder)

    def document_file_path(self, user_id: str, name: str) -> Path:
        """name phải là tên đã chuẩn hóa (documents.name). Phòng thủ thêm
        một lớp: path sau khi resolve phải nằm ngay trong thư mục của user."""
        user_dir = (self.documents_folder_path / user_id).resolve()
        path = (user_dir / f"{name}.pdf").resolve()
        if path.parent != user_dir:
            raise ValueError(f"Unsafe document name: {name!r}")
        return path


settings = Settings()  # type: ignore
