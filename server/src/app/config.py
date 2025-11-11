import os

from pydantic_settings import BaseSettings, SettingsConfigDict
from loguru import logger

ENV_PATH = os.path.join(os.getcwd(), ".env")
logger.debug(f"ENV_PATH: {ENV_PATH}")


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

    # ---- Database configure ----
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str

    # ---- Gemini setting ----
    gemini_api_key: str
    


settings = Settings()  # type: ignore