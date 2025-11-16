import os

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

    # ---- Gemini setting ----
    gemini_api_key: str

    # Helper database configure ----
    @property
    def db_uri(self) -> str:
        return f"mongodb://{self.mongo_user}:{self.mongo_password}@{self.mongo_host}:{self.mongo_port}/{self.mongo_db}?authSource=admin"


settings = Settings()  # type: ignore