from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from sqlalchemy.engine.url import URL


class AppConfig(BaseSettings):
    """Конфигурация приложения"""

    APP_NAME: str = Field(default="SaviorBill")
    APP_VERSION: str = Field(default="0.0.1dev")

    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=False)

    # DB
    DB_DRIVER: str = Field(default="postgresql+asyncpg")
    DB_USER: str = Field(default="aiosupport")
    DB_PASS: str
    DB_HOST: str = Field(default="localhost")
    DB_PORT: int = Field(default=5432)
    DB_NAME: str = Field(default="aiosupport")

    # Valkey / Redis
    VALKEY_HOST: str = Field(default="localhost")
    VALKEY_PORT: int = Field(default=6379)
    VALKEY_DB: int = Field(default=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

    @property
    def db_url(self) -> URL:
        """URL для подключения к БД"""
        return URL.create(
            drivername=self.DB_DRIVER,
            username=self.DB_USER,
            password=self.DB_PASS,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME
        )

    @property
    def valkey_url(self) -> str:
        """URL для подключения к Valkey"""
        return f"redis://{self.VALKEY_HOST}:{self.VALKEY_PORT}/{self.VALKEY_DB}"