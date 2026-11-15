"""Async Redis cache adapter supporting injected clients (e.g. fakeredis) and REDIS_URL."""

import inspect
import re
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import redis.asyncio as aioredis
from pydantic import SecretStr
from redis.asyncio import Redis
from redis.exceptions import RedisError

from commerce_ai.config.settings import redact_url_password
from commerce_ai.domain.errors import CacheStoreError

_URL_CREDENTIALS_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:/?#\s]*):([^\s/?#]+)@")
_QUERY_SECRET_RE = re.compile(r"([?&](?:password|pass|token)=)([^&#\s]+)", re.IGNORECASE)
_PASSWORD_KWARG_RE = re.compile(r"(password\s*=\s*['\"]?)([^'\",\s\)]+)(['\"]?)", re.IGNORECASE)


def extract_secret_password(redis_url: str | None) -> SecretStr | None:
    """Extract an optional URL password wrapped in SecretStr without exposing raw text."""
    if not redis_url:
        return None
    raw_password: str | None = None
    try:
        parsed = urlsplit(redis_url)
        raw_password = parsed.password
        _ = parsed.username
        _ = parsed.hostname
        _ = parsed.port
        _ = parsed.query
    except ValueError:
        if raw_password is None:
            match = _URL_CREDENTIALS_RE.search(redis_url)
            if match is not None:
                raw_password = match.group(2)
    if not raw_password:
        return None
    decoded = unquote(raw_password)
    return SecretStr(decoded) if decoded else None


def sanitize_redis_text(text: str, secret_password: SecretStr | None = None) -> str:
    """Strip any URL credentials, query secrets, or password arguments from Redis diagnostics."""
    sanitized = _URL_CREDENTIALS_RE.sub(r"\1:***@", text)
    sanitized = _QUERY_SECRET_RE.sub(r"\1***", sanitized)
    sanitized = _PASSWORD_KWARG_RE.sub(r"\1***\3", sanitized)
    if secret_password is not None:
        raw_secret = secret_password.get_secret_value()
        if raw_secret:
            sanitized = sanitized.replace(raw_secret, "***")
            encoded_secret = quote(raw_secret, safe="")
            if encoded_secret != raw_secret:
                sanitized = sanitized.replace(encoded_secret, "***")
    return sanitized


async def _resolve_awaitable(value: Any) -> Any:
    """Await Redis client method outputs whether typed as Awaitable or direct value."""
    if inspect.isawaitable(value):
        return await value
    return value


class RedisCacheStore:
    """Asynchronous Redis CacheStore wrapping operational failures in CacheStoreError."""

    def __init__(
        self,
        client: Redis | None = None,
        *,
        redis_url: str | None = None,
        socket_connect_timeout: float = 1.0,
        socket_timeout: float = 1.0,
    ) -> None:
        self._redacted_url: str | None = redact_url_password(redis_url)
        self._secret_password: SecretStr | None = extract_secret_password(redis_url)

        if client is not None:
            self._client: Redis = client
            self._owns_client = False
            return

        if redis_url is None or not redis_url.strip():
            raise CacheStoreError("Either a Redis client or a non-empty redis_url is required")

        try:
            self._client = aioredis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=socket_connect_timeout,
                socket_timeout=socket_timeout,
            )
        except (RedisError, ValueError, OSError) as exc:
            sanitized = sanitize_redis_text(str(exc), self._secret_password)
            raise CacheStoreError(
                f"Failed to initialize Redis client for {self._redacted_url}: {sanitized}"
            ) from exc
        self._owns_client = True

    def _wrap_error(self, operation: str, exc: Exception) -> CacheStoreError:
        sanitized = sanitize_redis_text(str(exc), self._secret_password)
        target = f" ({self._redacted_url})" if self._redacted_url else ""
        return CacheStoreError(f"Redis {operation} failed{target}: {sanitized}")

    async def ping(self) -> bool:
        """Check Redis server reachability."""
        try:
            return bool(await _resolve_awaitable(self._client.ping()))
        except (RedisError, OSError, TimeoutError) as exc:
            raise self._wrap_error("ping", exc) from exc

    async def get(self, key: str) -> str | None:
        """Fetch UTF-8 string value for key, or None if absent."""
        try:
            raw: Any = await _resolve_awaitable(self._client.get(key))
        except (RedisError, OSError, TimeoutError) as exc:
            raise self._wrap_error("get", exc) from exc

        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            try:
                return bytes(raw).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise CacheStoreError(
                    f"Redis get failed for key {key!r}: invalid UTF-8 payload"
                ) from exc
        return str(raw)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store UTF-8 string value with EX expiration; non-positive TTL deletes any stale key."""
        try:
            if ttl_seconds <= 0:
                await _resolve_awaitable(self._client.delete(key))
                return
            await _resolve_awaitable(self._client.set(key, value, ex=ttl_seconds))
        except (RedisError, OSError, TimeoutError) as exc:
            raise self._wrap_error("set", exc) from exc

    async def delete(self, key: str) -> None:
        """Delete key from Redis idempotently."""
        try:
            await _resolve_awaitable(self._client.delete(key))
        except (RedisError, OSError, TimeoutError) as exc:
            raise self._wrap_error("delete", exc) from exc

    async def aclose(self) -> None:
        """Close underlying Redis client connections when owned by this store."""
        if self._owns_client:
            await _resolve_awaitable(self._client.aclose())
