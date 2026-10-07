"""Application settings, loaded from environment variables / .env file."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from urllib.parse import quote_plus

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Library API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- Application ---------------------------------------------------------
    app_name: str = "Library API"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # -- Middleware ----------------------------------------------------------
    # Comma-separated in the environment: CORS_ALLOW_ORIGINS=http://a.com,http://b.com
    # NoDecode stops pydantic-settings from JSON-parsing the raw env value
    # (which would reject the plain `*`), leaving it to the validator below.
    cors_allow_origins: Annotated[list[str], NoDecode] = ["*"]

    # Rate limiting: 10 requests per client per minute by default.
    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=10, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    # Only enable behind a reverse proxy you control: it makes the limiter trust
    # the client-supplied X-Forwarded-For header.
    trust_proxy_headers: bool = False

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # -- Database ------------------------------------------------------------
    # Either provide a full DATABASE_URL, or the individual POSTGRES_* parts.
    database_url: str | None = None
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "library"

    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800

    # -- Library business rules ---------------------------------------------
    loan_period_days: int = Field(default=14, ge=1, le=365)
    max_active_loans_per_member: int = Field(default=5, ge=1, le=100)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_testing(self) -> bool:
        return self.environment.lower() == "test"

    def _build_url(self, driver: str) -> str:
        if self.database_url:
            # Allow a plain `postgresql://` URL and swap in the async driver.
            if driver.startswith("postgresql+asyncpg") and self.database_url.startswith(
                "postgresql://"
            ):
                return self.database_url.replace("postgresql://", f"{driver}://", 1)
            return self.database_url
        password = f":{quote_plus(self.postgres_password)}" if self.postgres_password else ""
        return (
            f"{driver}://{quote_plus(self.postgres_user)}{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async URL used by the application and Alembic."""
        return self._build_url("postgresql+asyncpg")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
