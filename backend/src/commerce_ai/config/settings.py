"""Typed runtime configuration loaded safely via pydantic-settings."""

import ipaddress
import json
import re
from collections.abc import Iterator
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, SecretStr, ValidationInfo, field_serializer, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from commerce_ai.config.scoring import ScoringConfig

_INLINE_COMMENT_RE = re.compile(r"\s+#")
_FALLBACK_URL_SECRET_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:/?#\s]*):([^\s/?#]+)@")
_QUERY_SECRET_RE = re.compile(
    r"([?&](?:password|passwd|pwd|pass|token|secret|api[_-]?key)=)([^&#\s]+)",
    re.IGNORECASE,
)


def _parse_string_list_setting(value: Any, *, field_name: str) -> Any:
    """Parse comma-separated strings, JSON arrays, or sequences while stripping '#' comments."""
    if isinstance(value, str):
        cleaned = _strip_inline_comment(value)
        if not cleaned:
            return []
        if cleaned.startswith("["):
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{field_name} must be valid JSON or CSV") from exc
            if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
                raise ValueError(f"{field_name} JSON must be a list of strings")
            return [item.strip() for item in parsed if item.strip()]
        return [part.strip() for part in cleaned.split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"{field_name} items must be strings")
            cleaned_item = _strip_inline_comment(item)
            if cleaned_item:
                items.append(cleaned_item)
        return items
    return value


def _mask_query_secrets(text: str) -> str:
    return _QUERY_SECRET_RE.sub(r"\1***", text)


def _redact_fallback_url(url: str) -> str:
    return _mask_query_secrets(_FALLBACK_URL_SECRET_RE.sub(r"\1:***@", url))


def _strip_inline_comment(raw: str) -> str:
    """Strip inline '# ...' comments (preceded by whitespace or at start) and outer spaces."""
    if raw.lstrip().startswith("#"):
        return ""
    return _INLINE_COMMENT_RE.split(raw, maxsplit=1)[0].strip()


def redact_url_password(url: str | None) -> str | None:
    """Mask any password component or sensitive query parameter in a connection URL."""
    if url is None:
        return None
    try:
        parsed = urlsplit(url)
        raw_password = parsed.password
        raw_username = parsed.username
        raw_hostname = parsed.hostname
        raw_port = parsed.port
        raw_scheme = parsed.scheme
        raw_netloc = parsed.netloc
        raw_path = parsed.path
        raw_query = parsed.query
        raw_fragment = parsed.fragment
    except ValueError:
        return _redact_fallback_url(url)

    masked_query = _mask_query_secrets(f"?{raw_query}")[1:] if raw_query else raw_query
    if raw_password is None:
        if masked_query == raw_query:
            return url
        return urlunsplit((raw_scheme, raw_netloc, raw_path, masked_query, raw_fragment))

    if raw_hostname is None:
        return _redact_fallback_url(url)

    user_part = raw_username or ""
    host_part = f"[{raw_hostname}]" if ":" in raw_hostname else raw_hostname
    port_part = f":{raw_port}" if raw_port is not None else ""
    masked_netloc = f"{user_part}:***@{host_part}{port_part}"
    return urlunsplit((raw_scheme, masked_netloc, raw_path, masked_query, raw_fragment))


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables or .env without secret leaks."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    serper_api_key: SecretStr | None = None
    redis_url: str | None = None
    catalog_mode: Literal["auto", "seed", "serper"] = "auto"
    cache_ttl_seconds: int = Field(default=1800, gt=0)
    serper_timeout_seconds: float = Field(default=2.0, gt=0.0, allow_inf_nan=False)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)

    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    llm_mode: Literal["auto", "fake", "live"] = "auto"
    explain_mode: Literal["auto", "llm", "template"] = "auto"
    llm_primary_model: str = "gemini/gemini-2.5-flash"
    llm_fallback_model: str | None = "groq/llama-3.3-70b-versatile"
    llm_timeout_seconds: float = Field(default=8.0, gt=0.0, allow_inf_nan=False)
    guardrail_max_chars: int = Field(default=1000, ge=50, le=4000)

    database_url: str = "sqlite+aiosqlite:///./commerce_ai.db"
    session_ttl_seconds: int = Field(default=86400, gt=0)
    session_max_turns: int = Field(default=10, ge=2, le=50)
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    rate_limit_rpm: int = Field(default=60, ge=0)
    trusted_proxy_cidrs: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["127.0.0.1/32", "::1/128"]
    )

    @field_validator(
        "serper_api_key",
        "gemini_api_key",
        "groq_api_key",
        "openai_api_key",
        mode="before",
    )
    @classmethod
    def _clean_optional_secret(cls, value: Any) -> Any:
        if isinstance(value, SecretStr):
            return None if not value.get_secret_value().strip() else value
        if isinstance(value, str):
            cleaned = _strip_inline_comment(value)
            return None if cleaned == "" else cleaned
        return value

    @field_validator("redis_url", "llm_fallback_model", mode="before")
    @classmethod
    def _clean_optional_str(cls, value: Any) -> Any:
        if isinstance(value, str):
            cleaned = _strip_inline_comment(value)
            return None if cleaned == "" else cleaned
        return value

    @field_validator("database_url", "llm_primary_model", mode="before")
    @classmethod
    def _clean_required_non_empty_str(cls, value: Any, info: ValidationInfo) -> Any:
        if isinstance(value, str):
            cleaned = _strip_inline_comment(value)
            if not cleaned:
                raise ValueError(f"{info.field_name} must not be empty")
            return cleaned
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _clean_cors_allowed_origins(cls, value: Any) -> Any:
        return _parse_string_list_setting(value, field_name="cors_allowed_origins")

    @field_validator("trusted_proxy_cidrs", mode="before")
    @classmethod
    def _clean_trusted_proxy_cidrs(cls, value: Any) -> Any:
        parsed = _parse_string_list_setting(value, field_name="trusted_proxy_cidrs")
        if not isinstance(parsed, list):
            return parsed
        validated: list[str] = []
        for entry in parsed:
            try:
                network = ipaddress.ip_network(entry, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid CIDR in trusted_proxy_cidrs: {entry!r}") from exc
            validated.append(str(network))
        return validated

    @field_validator(
        "app_env",
        "log_level",
        "catalog_mode",
        "llm_mode",
        "explain_mode",
        "cache_ttl_seconds",
        "serper_timeout_seconds",
        "llm_timeout_seconds",
        "guardrail_max_chars",
        "session_ttl_seconds",
        "session_max_turns",
        "rate_limit_rpm",
        mode="before",
    )
    @classmethod
    def _clean_scalar_env_str(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _strip_inline_comment(value)
        return value

    @field_serializer("redis_url", "database_url", when_used="always")
    def _serialize_redacted_url(self, value: str | None) -> str | None:
        return redact_url_password(value)

    def __repr_args__(self) -> Iterator[tuple[str | None, Any]]:
        for name, value in super().__repr_args__():
            if name in {"redis_url", "database_url"} and isinstance(value, str):
                yield name, redact_url_password(value)
            else:
                yield name, value

    def safe_summary(self) -> dict[str, Any]:
        """Return a credential-redacted configuration dictionary safe for diagnostics/logs."""
        return {
            "app_env": self.app_env,
            "log_level": self.log_level,
            "serper_api_key": "***" if self.serper_api_key is not None else None,
            "gemini_api_key": "***" if self.gemini_api_key is not None else None,
            "groq_api_key": "***" if self.groq_api_key is not None else None,
            "openai_api_key": "***" if self.openai_api_key is not None else None,
            "redis_url": redact_url_password(self.redis_url),
            "database_url": redact_url_password(self.database_url),
            "catalog_mode": self.catalog_mode,
            "llm_mode": self.llm_mode,
            "explain_mode": self.explain_mode,
            "llm_primary_model": self.llm_primary_model,
            "llm_fallback_model": self.llm_fallback_model,
            "llm_timeout_seconds": self.llm_timeout_seconds,
            "guardrail_max_chars": self.guardrail_max_chars,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "serper_timeout_seconds": self.serper_timeout_seconds,
            "session_ttl_seconds": self.session_ttl_seconds,
            "session_max_turns": self.session_max_turns,
            "cors_allowed_origins": list(self.cors_allowed_origins),
            "rate_limit_rpm": self.rate_limit_rpm,
            "trusted_proxy_cidrs": list(self.trusted_proxy_cidrs),
            "scoring": self.scoring.model_dump(),
        }
