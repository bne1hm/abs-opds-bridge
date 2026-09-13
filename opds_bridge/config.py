from functools import lru_cache
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ABS_BASE: AnyHttpUrl = "http://localhost:13378"
    ABS_TOKEN: str | None = None

    OPDS_BASIC_USER: str | None = None
    OPDS_BASIC_PASS: str | None = None

    CACHE_TTL_DEFAULT: int = 30
    INDEX_TTL: int = 600

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
