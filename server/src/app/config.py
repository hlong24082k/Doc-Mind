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

    # ---- Secrect Token ----
    jwt_secret_key: str
    jwt_algorithm: str

    # ---- Database configure ----
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str

    # ---- Gemini setting ----
    gemini_api_key: str

    # ---- Help Database configure ----
    @property
    def mysql_url(self) -> str:
        return (
            "mysql+pymysql://"
            f"{self.mysql_user}:{self.mysql_password}@"
            f"{self.mysql_host}:{self.mysql_port}/"
            f"{self.mysql_database}"
        )
    


settings = Settings()  # type: ignore