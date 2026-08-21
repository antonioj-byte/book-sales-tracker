from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    keepa_api_key: str = Field(..., alias="KEEPA_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    google_books_api_key: str | None = Field(default=None, alias="GOOGLE_BOOKS_API_KEY")

    @property
    def has_gemini(self) -> bool:
        return bool((self.gemini_api_key or "").strip())

    default_amazon_domain: str = Field(default="es", alias="DEFAULT_AMAZON_DOMAIN")
    gemini_model: str = Field(default="gemini-3.5-flash-lite", alias="GEMINI_MODEL")
    output_language: str = Field(default="es", alias="OUTPUT_LANGUAGE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
