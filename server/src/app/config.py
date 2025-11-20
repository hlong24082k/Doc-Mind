import os

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_PATH = os.path.join(os.getcwd(), ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Project Information -----
    name: str
    version: str
    description: str
    author: str
    debug: bool

    # ---- Server configure ----
    host: str
    port: int

    # ---- Secrect Token ----
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int

    # ---- Database configure ----
    mongo_host: str
    mongo_port: int
    mongo_user: str
    mongo_password: str
    max_connections_count: int
    min_connections_count: int
    mongo_db: str

    # ---- Documents folfer ----
    documents_folder: str

    # ---- Gemini setting ----
    gemini_api_key: str

    # Helper database configure ----
    @property
    def db_uri(self) -> str:
        return f"mongodb://{self.mongo_user}:{self.mongo_password}@{self.mongo_host}:{self.mongo_port}/{self.mongo_db}?authSource=admin"

    # Helper Documents folfer ----
    @property
    def documents_folder_path(self) -> Path:
        return Path(self.documents_folder)

    def get_document_with_path(self, filename: str) -> Path:
        return self.documents_folder_path / filename

settings = Settings()  # type: ignore
