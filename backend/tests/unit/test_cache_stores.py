"""Offline unit & edge-case tests for InMemoryTTLCache, RedisCacheStore, and cache factory."""

import logging
from typing import Any, cast

import fakeredis.aioredis
import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from commerce_ai.adapters.cache import redis_store as redis_store_module
from commerce_ai.adapters.cache.factory import create_cache_store
from commerce_ai.adapters.cache.memory import InMemoryTTLCache
from commerce_ai.adapters.cache.redis_store import RedisCacheStore, sanitize_redis_text
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.errors import CacheStoreError
from commerce_ai.domain.ports import CacheStore


class _FakeMonotonicClock:
    """Deterministic monotonic clock stub for instant TTL testing."""

    def __init__(self, initial: float = 100.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def test_in_memory_cache_ttl_lifecycle() -> None:
    """T1.2 — InMemoryTTLCache stores strings, respects monotonic TTL expiry, and deletes."""
    clock = _FakeMonotonicClock()
    cache = InMemoryTTLCache(clock=clock)
    assert isinstance(cache, CacheStore)

    assert await cache.get("missing") is None

    await cache.set("k1", '{"ok":true}', ttl_seconds=30)
    assert await cache.get("k1") == '{"ok":true}'

    clock.advance(29.9)
    assert await cache.get("k1") == '{"ok":true}'

    clock.advance(0.1)
    assert await cache.get("k1") is None

    await cache.set("k2", "v2", ttl_seconds=60)
    assert await cache.get("k2") == "v2"
    await cache.delete("k2")
    assert await cache.get("k2") is None


async def test_in_memory_cache_edge_cases() -> None:
    """T3.7 — delete() safety, ttl<=0 purge, max_entries validation, expired sweep & LRU."""
    with pytest.raises(ValueError):
        InMemoryTTLCache(max_entries=0)
    with pytest.raises(ValueError):
        InMemoryTTLCache(max_entries=-3)

    clock = _FakeMonotonicClock()
    cache = InMemoryTTLCache(clock=clock, max_entries=2)

    await cache.delete("nonexistent-key")

    await cache.set("k1", "stale-value", ttl_seconds=60)
    assert await cache.get("k1") == "stale-value"

    await cache.set("k1", "new-value", ttl_seconds=0)
    assert await cache.get("k1") is None

    await cache.set("k2", "negative-ttl", ttl_seconds=-5)
    assert await cache.get("k2") is None

    # LRU eviction promotes accessed keys and evicts oldest untouched entry when full.
    await cache.set("a", "1", ttl_seconds=60)
    await cache.set("b", "2", ttl_seconds=60)
    assert await cache.get("a") == "1"  # "a" becomes MRU; "b" becomes LRU
    await cache.set("c", "3", ttl_seconds=60)
    assert await cache.get("b") is None
    assert await cache.get("a") == "1"
    assert await cache.get("c") == "3"

    # Expired entries are pruned at capacity before evicting still-valid entries.
    lru_clock = _FakeMonotonicClock()
    ttl_lru = InMemoryTTLCache(clock=lru_clock, max_entries=2)
    await ttl_lru.set("short", "old", ttl_seconds=5)
    await ttl_lru.set("long", "keep", ttl_seconds=60)
    lru_clock.advance(10.0)
    await ttl_lru.set("fresh", "new", ttl_seconds=60)
    assert await ttl_lru.get("long") == "keep"
    assert await ttl_lru.get("fresh") == "new"


async def test_redis_cache_store_with_fakeredis() -> None:
    """T1.3 — RedisCacheStore handles UTF-8 payloads, EX TTL, and delete via fakeredis."""
    for decode_responses in (False, True):
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=decode_responses)
        store = RedisCacheStore(client=fake_redis)
        assert isinstance(store, CacheStore)
        assert await store.ping() is True
        assert await store.get("missing") is None

        payload = '{"query":"سماعة بلوتوث","price":"1499.50"}'
        await store.set("eg:both:earbuds:none:none", payload, ttl_seconds=120)
        assert await store.get("eg:both:earbuds:none:none") == payload

        ttl = await fake_redis.ttl("eg:both:earbuds:none:none")
        assert 0 < ttl <= 120

        await store.set("eg:both:earbuds:none:none", "replaced", ttl_seconds=0)
        assert await store.get("eg:both:earbuds:none:none") is None

        await store.set("delete-me", "bye", ttl_seconds=60)
        await store.delete("delete-me")
        assert await store.get("delete-me") is None

        await fake_redis.aclose()


async def test_redis_cache_error_wrapping_and_secret_redaction(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T3.6 — RedisCacheStore validates init args/UTF-8 and wraps errors without secret leaks."""
    with pytest.raises(CacheStoreError):
        RedisCacheStore()
    with pytest.raises(CacheStoreError):
        RedisCacheStore(redis_url="   ")

    class _FailingRedisClient:
        async def ping(self) -> bool:
            raise RedisConnectionError(
                "Error connecting to redis://user:p@ss:w%40rd@localhost:6379/0?token=tok123"
            )

        async def get(self, key: str) -> Any:
            if key == "bad-utf8":
                return b"\xff\xfe\xfd"
            raise RedisError(f"GET failed for {key} on redis://user:p@ss:w%40rd@localhost:6379/0")

        async def set(self, key: str, value: str, ex: int | None = None) -> bool:
            raise RedisError(
                "SET failed (password='p@ss:w%40rd', url=redis://user:p@ss:w%40rd@localhost:6379/0)"
            )

        async def delete(self, key: str) -> int:
            raise RedisError(f"DEL failed for {key} at redis://user:p@ss:w%40rd@localhost:6379/0")

    failing_client = cast(Redis, _FailingRedisClient())
    store = RedisCacheStore(
        client=failing_client,
        redis_url="redis://user:p@ss:w%40rd@localhost:6379/0",
    )

    with pytest.raises(CacheStoreError, match="invalid UTF-8 payload"):
        await store.get("bad-utf8")

    with caplog.at_level(logging.DEBUG):
        for coro in (
            store.ping(),
            store.get("test-key"),
            store.set("test-key", "value", 60),
            store.delete("test-key"),
        ):
            with pytest.raises(CacheStoreError) as exc_info:
                await coro
            assert "p@ss" not in str(exc_info.value)
            assert "w@rd" not in str(exc_info.value)
            assert "w%40rd" not in str(exc_info.value)
            assert "tok123" not in str(exc_info.value)
            assert "***" in str(exc_info.value)

    assert "p@ss" not in caplog.text
    assert "w@rd" not in caplog.text
    assert "tok123" not in caplog.text
    assert "qsec" not in sanitize_redis_text(
        "connecting redis://host/0?password=qsec&pass=psec&token=tsec"
    )


async def test_cache_factory_defaults_to_memory_when_redis_url_unset() -> None:
    """T1.4 — Cache factory returns InMemoryTTLCache when REDIS_URL is unset or empty."""
    for redis_url in (None, "", "   "):
        settings = AppSettings(_env_file=None, redis_url=redis_url)
        store = await create_cache_store(settings)
        assert isinstance(store, InMemoryTTLCache)

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    configured = AppSettings(_env_file=None, redis_url="redis://localhost:6379/0")
    redis_store = await create_cache_store(configured, redis_client=fake_redis)
    assert isinstance(redis_store, RedisCacheStore)
    await fake_redis.aclose()


async def test_cache_factory_falls_back_when_redis_unreachable(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T3.8 — Cache factory falls back cleanly on mocked unreachable & malformed REDIS_URLs."""
    aclose_called = False

    class _OwnedFailingRedis:
        async def ping(self) -> Any:
            raise RedisConnectionError("connection refused redis://:secretpass@127.0.0.1:6399/0")

        async def aclose(self) -> None:
            nonlocal aclose_called
            aclose_called = True

    monkeypatch.setattr(
        redis_store_module.aioredis,
        "from_url",
        lambda *_args, **_kwargs: _OwnedFailingRedis(),
    )

    settings = AppSettings(
        _env_file=None,
        redis_url="redis://:secretpass@127.0.0.1:6399/0",
    )
    with caplog.at_level(logging.WARNING):
        store = await create_cache_store(settings, ping_timeout_seconds=0.1)

    assert isinstance(store, InMemoryTTLCache)
    assert aclose_called is True
    assert "secretpass" not in caplog.text
    assert "***" in caplog.text

    await store.set("fallback-key", "works", ttl_seconds=60)
    assert await store.get("fallback-key") == "works"

    # Malformed-port REDIS_URL also falls back cleanly without uncaught ValueError or leaks.
    caplog.clear()
    bad_port_settings = AppSettings(
        _env_file=None,
        redis_url="redis://user:p@ss:secret@127.0.0.1:badport/0?password=qsec",
    )
    with caplog.at_level(logging.WARNING):
        bad_port_store = await create_cache_store(bad_port_settings, ping_timeout_seconds=0.1)

    assert isinstance(bad_port_store, InMemoryTTLCache)
    assert "p@ss:secret" not in caplog.text
    assert "qsec" not in caplog.text
    assert "***" in caplog.text

    class _PingFailingRedis:
        async def ping(self) -> Any:
            raise RedisConnectionError("connection refused redis://:secretpass@127.0.0.1:6399/0")

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        injected_fallback = await create_cache_store(
            settings,
            redis_client=cast(Redis, _PingFailingRedis()),
            ping_timeout_seconds=0.1,
        )

    assert isinstance(injected_fallback, InMemoryTTLCache)
    assert "secretpass" not in caplog.text
