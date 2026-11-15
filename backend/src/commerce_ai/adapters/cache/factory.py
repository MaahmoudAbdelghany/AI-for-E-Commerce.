"""Cache factory resolving RedisCacheStore with automatic InMemoryTTLCache fallback."""

import asyncio
import contextlib
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from commerce_ai.adapters.cache.memory import InMemoryTTLCache
from commerce_ai.adapters.cache.redis_store import (
    RedisCacheStore,
    extract_secret_password,
    sanitize_redis_text,
)
from commerce_ai.config.settings import AppSettings, redact_url_password
from commerce_ai.domain.errors import CacheStoreError
from commerce_ai.domain.ports import CacheStore

logger = logging.getLogger(__name__)


async def create_cache_store(
    settings: AppSettings,
    redis_client: Redis | None = None,
    *,
    ping_timeout_seconds: float = 1.0,
) -> CacheStore:
    """Return RedisCacheStore when configured and reachable; otherwise fall back to memory."""
    secret_pw = extract_secret_password(settings.redis_url)

    if redis_client is not None:
        injected_store = RedisCacheStore(
            client=redis_client,
            redis_url=settings.redis_url,
            socket_connect_timeout=ping_timeout_seconds,
            socket_timeout=ping_timeout_seconds,
        )
        try:
            await asyncio.wait_for(injected_store.ping(), timeout=ping_timeout_seconds)
            return injected_store
        except (CacheStoreError, RedisError, OSError, TimeoutError) as exc:
            redacted = redact_url_password(settings.redis_url) or "injected Redis client"
            safe_reason = sanitize_redis_text(str(exc), secret_pw)
            logger.warning(
                "Redis cache unavailable (%s); falling back to InMemoryTTLCache: %s",
                redacted,
                safe_reason,
            )
            return InMemoryTTLCache()

    if not settings.redis_url:
        return InMemoryTTLCache()

    redacted_url: str | None = None
    owned_store: RedisCacheStore | None = None
    try:
        redacted_url = redact_url_password(settings.redis_url)
        owned_store = RedisCacheStore(
            redis_url=settings.redis_url,
            socket_connect_timeout=ping_timeout_seconds,
            socket_timeout=ping_timeout_seconds,
        )
        await asyncio.wait_for(owned_store.ping(), timeout=ping_timeout_seconds)
        return owned_store
    except (CacheStoreError, RedisError, OSError, TimeoutError, ValueError) as exc:
        if owned_store is not None:
            with contextlib.suppress(RedisError, OSError, CacheStoreError):
                await owned_store.aclose()
        if redacted_url is None:
            redacted_url = redact_url_password(settings.redis_url)
        safe_reason = sanitize_redis_text(str(exc), secret_pw)
        logger.warning(
            "Redis cache unreachable at %s; falling back to InMemoryTTLCache (%s)",
            redacted_url,
            safe_reason,
        )
        return InMemoryTTLCache()
