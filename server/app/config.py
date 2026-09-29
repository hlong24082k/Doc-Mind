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

    # ---- Gemini setting ----
    gemini_api_key: str = ""

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

    def get_document_with_path(self, filename: str) -> Path:
        return self.documents_folder_path / filename


settings = Settings()  # type: ignore
