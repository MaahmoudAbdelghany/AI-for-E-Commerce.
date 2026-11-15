"""Typed runtime configuration loaded safely via pydantic-settings."""

import re
from collections.abc import Iterator
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from commerce_ai.config.scoring import ScoringConfig

_INLINE_COMMENT_RE = re.compile(r"\s+#")
_FALLBACK_URL_SECRET_RE = re.compile(r":([^:@/\s]+)@")


def _strip_inline_comment(raw: str) -> str:
    """Strip inline '# ...' comments (preceded by whitespace or at start) and outer spaces."""
    if raw.lstrip().startswith("#"):
        return ""
    return _INLINE_COMMENT_RE.split(raw, maxsplit=1)[0].strip()


def redact_url_password(url: str | None) -> str | None:
    """Mask any password component in a connection URL before logging or formatting."""
    if url is None:
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return _FALLBACK_URL_SECRET_RE.sub(":***@", url)

    if parsed.password is None:
        return url

    if parsed.hostname is None:
        return _FALLBACK_URL_SECRET_RE.sub(":***@", url)

    user_part = parsed.username or ""
    host_part = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    port_part = f":{parsed.port}" if parsed.port is not None else ""
    masked_netloc = f"{user_part}:***@{host_part}{port_part}"
    return urlunsplit((parsed.scheme, masked_netloc, parsed.path, parsed.query, parsed.fragment))


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables or .env without secret leaks."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    serper_api_key: SecretStr | None = None
    redis_url: str | None = None
    catalog_mode: Literal["auto", "seed", "serper"] = "auto"
    cache_ttl_seconds: int = Field(default=1800, gt=0)
    serper_timeout_seconds: float = Field(default=2.0, gt=0.0, allow_inf_nan=False)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)

    @field_validator("serper_api_key", mode="before")
    @classmethod
    def _clean_serper_api_key(cls, value: Any) -> Any:
        if isinstance(value, SecretStr):
            return None if not value.get_secret_value().strip() else value
        if isinstance(value, str):
            cleaned = _strip_inline_comment(value)
            return None if cleaned == "" else cleaned
        return value

    @field_validator("redis_url", mode="before")
    @classmethod
    def _clean_redis_url(cls, value: Any) -> Any:
        if isinstance(value, str):
            cleaned = _strip_inline_comment(value)
            return None if cleaned == "" else cleaned
        return value

    @field_validator("catalog_mode", "cache_ttl_seconds", "serper_timeout_seconds", mode="before")
    @classmethod
    def _clean_scalar_env_str(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _strip_inline_comment(value)
        return value

    def __repr_args__(self) -> Iterator[tuple[str | None, Any]]:
        for name, value in super().__repr_args__():
            if name == "redis_url" and isinstance(value, str):
                yield name, redact_url_password(value)
            else:
                yield name, value

    def safe_summary(self) -> dict[str, Any]:
        """Return a credential-redacted configuration dictionary safe for diagnostics/logs."""
        return {
            "serper_api_key": "***" if self.serper_api_key is not None else None,
            "redis_url": redact_url_password(self.redis_url),
            "catalog_mode": self.catalog_mode,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "serper_timeout_seconds": self.serper_timeout_seconds,
            "scoring": self.scoring.model_dump(),
        }
