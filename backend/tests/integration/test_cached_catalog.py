"""Offline integration tests for CachedCatalogProvider, cache stores, and factories."""

import asyncio
from decimal import Decimal

import fakeredis.aioredis
import httpx
import pytest
from pydantic import SecretStr

from commerce_ai.adapters.cache import redis_store as redis_store_module
from commerce_ai.adapters.cache.factory import create_cache_store
from commerce_ai.adapters.cache.memory import InMemoryTTLCache
from commerce_ai.adapters.cache.redis_store import RedisCacheStore
from commerce_ai.adapters.catalog.cached_provider import CachedCatalogProvider
from commerce_ai.adapters.catalog.factory import create_catalog_provider
from commerce_ai.adapters.catalog.seed_provider import SeedCatalogProvider
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.errors import CacheStoreError, CatalogProviderError
from commerce_ai.domain.models import (
    CatalogSearchResult,
    CatalogSourceMode,
    CountryCode,
    SearchIntent,
    StoreFilter,
)
from commerce_ai.domain.ports import CacheStore, CatalogProvider


class _SpyCatalogProvider:
    """Counting spy wrapping any CatalogProvider."""

    def __init__(self, inner: CatalogProvider) -> None:
        self._inner = inner
        self.call_count = 0

    async def search_offers(self, intent: SearchIntent) -> CatalogSearchResult:
        self.call_count += 1
        return await self._inner.search_offers(intent)


async def test_cached_seed_catalog_miss_then_hit() -> None:
    """T2.1 — CachedCatalogProvider misses once, caches under normalized key, and hits next."""
    spy = _SpyCatalogProvider(SeedCatalogProvider())
    cache = InMemoryTTLCache()
    cached = CachedCatalogProvider(provider=spy, cache=cache, ttl_seconds=1800)

    intent = SearchIntent(query="Anker earbuds", country=CountryCode.EG, store=StoreFilter.BOTH)
    first = await cached.search_offers(intent)
    assert spy.call_count == 1
    assert first.cache_hit is False
    assert first.source_mode == CatalogSourceMode.SEED
    assert len(first.offers) >= 6

    cached_json = await cache.get(intent.catalog_cache_key())
    assert cached_json is not None

    second = await cached.search_offers(
        SearchIntent(query="  anker   EARBUDS! ", country=CountryCode.EG, store=StoreFilter.BOTH)
    )
    assert spy.call_count == 1
    assert second.cache_hit is True
    assert second.source_mode == CatalogSourceMode.SEED
    assert second.offers == first.offers


async def test_cached_live_serper_with_fakeredis() -> None:
    """T2.2 — CachedCatalogProvider + fakeredis + MockTransport runs 1 HTTP call across hits."""
    http_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal http_calls
        http_calls += 1
        return httpx.Response(
            200,
            json={
                "shopping": [
                    {
                        "title": "Anker Soundcore Liberty 4 NC",
                        "source": "Amazon.sa",
                        "link": "https://www.amazon.sa/dp/B0TESTSA1",
                        "price": "SAR 279.00",
                        "rating": 4.8,
                        "ratingCount": 510,
                        "productId": "sa-live-1",
                    },
                    {
                        "title": "Anker Soundcore R50i",
                        "source": "Noon Saudi",
                        "link": "https://www.google.com/shopping/product/sa-google-1",
                        "price": "SAR 99.00",
                        "rating": 4.6,
                        "ratingCount": 300,
                        "productId": "sa-live-2",
                    },
                ]
            },
        )

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache_store = RedisCacheStore(client=fake_redis)
    settings = AppSettings(
        _env_file=None,
        catalog_mode="serper",
        serper_api_key=SecretStr("test-key-offline"),
        cache_ttl_seconds=900,
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = create_catalog_provider(settings, cache=cache_store, http_client=client)
        assert isinstance(provider, CachedCatalogProvider)

        intent = SearchIntent(query="سماعة أنكر", country=CountryCode.SA)
        first = await provider.search_offers(intent)
        assert http_calls == 1
        assert first.source_mode == CatalogSourceMode.LIVE
        assert first.cache_hit is False
        assert len(first.offers) == 2

        # Verify fakeredis holds the serialized entry with TTL.
        ttl = await fake_redis.ttl(intent.catalog_cache_key())
        assert 0 < ttl <= 900

        second = await provider.search_offers(
            SearchIntent(query="  سَمَاعَةُ   أنْكَر! ", country=CountryCode.SA)
        )
        assert http_calls == 1
        assert second.source_mode == CatalogSourceMode.LIVE
        assert second.cache_hit is True
        assert second.offers == first.offers
        assert second.offers[1].url == "https://www.google.com/shopping/product/sa-google-1"

    await fake_redis.aclose()


async def test_factories_wire_fallback_cache_and_seed_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2.3 — Unreachable Redis falls back to InMemoryTTLCache + SeedCatalogProvider end-to-end."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    class _UnavailableRedisClient:
        async def ping(self) -> bool:
            raise RedisConnectionError("mock unreachable redis")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        redis_store_module.aioredis,
        "from_url",
        lambda *_args, **_kwargs: _UnavailableRedisClient(),
    )

    settings = AppSettings(
        _env_file=None,
        redis_url="redis://127.0.0.1:6399/0",
        catalog_mode="auto",
        serper_api_key=None,
    )
    cache = await create_cache_store(settings, ping_timeout_seconds=0.1)
    assert isinstance(cache, InMemoryTTLCache)

    provider = create_catalog_provider(settings, cache=cache)
    assert isinstance(provider, CachedCatalogProvider)

    intent = SearchIntent(query="iPhone 15", country=CountryCode.AE)
    miss = await provider.search_offers(intent)
    assert miss.source_mode == CatalogSourceMode.SEED
    assert miss.cache_hit is False
    assert len(miss.offers) >= 1

    hit = await provider.search_offers(intent)
    assert hit.source_mode == CatalogSourceMode.SEED
    assert hit.cache_hit is True
    assert hit.offers == miss.offers


async def test_cached_catalog_error_resilience_and_no_error_caching() -> None:
    """T3.5 — Provider errors never cache; cache read/write/corrupt failures degrade cleanly."""
    seed_provider = SeedCatalogProvider()
    intent = SearchIntent(query="Anker earbuds", country=CountryCode.EG)

    class _FlakyProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def search_offers(self, search_intent: SearchIntent) -> CatalogSearchResult:
            self.calls += 1
            if self.calls == 1:
                raise CatalogProviderError(provider="serper", retriable=True, reason="timeout")
            return await seed_provider.search_offers(search_intent)

    # (a) CatalogProviderError propagates and writes nothing to cache.
    clean_cache = InMemoryTTLCache()
    flaky = _FlakyProvider()
    cached_flaky = CachedCatalogProvider(provider=flaky, cache=clean_cache)

    with pytest.raises(CatalogProviderError):
        await cached_flaky.search_offers(intent)
    assert await clean_cache.get(intent.catalog_cache_key()) is None

    recovered = await cached_flaky.search_offers(intent)
    assert flaky.calls == 2
    assert recovered.cache_hit is False
    assert len(recovered.offers) >= 6

    # (b1) Corrupt JSON in cache degrades gracefully to underlying provider.
    corrupt_cache = InMemoryTTLCache()
    await corrupt_cache.set(intent.catalog_cache_key(), "{not-valid-json", ttl_seconds=60)
    cached_corrupt = CachedCatalogProvider(provider=seed_provider, cache=corrupt_cache)
    res_from_corrupt = await cached_corrupt.search_offers(intent)
    assert res_from_corrupt.cache_hit is False
    assert len(res_from_corrupt.offers) >= 6

    # (b2) CacheStore.get() and CacheStore.set() raising CacheStoreError degrade cleanly.
    class _FailingCache:
        async def get(self, key: str) -> str | None:
            raise CacheStoreError("redis get failed")

        async def set(self, key: str, value: str, ttl_seconds: int) -> None:
            raise CacheStoreError("redis set failed")

        async def delete(self, key: str) -> None:
            raise CacheStoreError("redis delete failed")

    failing_cache = _FailingCache()
    assert isinstance(failing_cache, CacheStore)
    cached_broken = CachedCatalogProvider(provider=seed_provider, cache=failing_cache)
    res_degraded = await cached_broken.search_offers(intent)
    assert res_degraded.cache_hit is False
    assert len(res_degraded.offers) >= 6


async def test_cached_catalog_key_reuse_and_language_isolation() -> None:
    """T2.1 — Budget/rating refinements & Arabic orthography hit cache; ar/en isolate."""
    spy = _SpyCatalogProvider(SeedCatalogProvider())
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = RedisCacheStore(client=fake_redis)
    cached = CachedCatalogProvider(provider=spy, cache=cache, ttl_seconds=900)
    try:
        ar_base = SearchIntent(query="سماعة أنكر", country=CountryCode.EG, language="ar")
        res1 = await cached.search_offers(ar_base)
        assert res1.cache_hit is False
        assert spy.call_count == 1

        # Arabic orthographic folding + budget/rating refinements reuse the same catalog entry.
        ar_refined = SearchIntent(
            query="سماعه انكر",
            country=CountryCode.EG,
            max_budget=Decimal("2500"),
            min_rating=4.5,
            language="ar",
        )
        res2 = await cached.search_offers(ar_refined)
        assert res2.cache_hit is True
        assert res2.offers == res1.offers
        assert spy.call_count == 1

        # Distinct language ('en' vs 'ar') must not collide in catalog_cache_key().
        en_same_text = SearchIntent(query="سماعة أنكر", country=CountryCode.EG, language="en")
        res3 = await cached.search_offers(en_same_text)
        assert res3.cache_hit is False
        assert spy.call_count == 2
        assert ar_base.catalog_cache_key() != en_same_text.catalog_cache_key()
    finally:
        await fake_redis.aclose()


async def test_cached_catalog_single_flight_coalescing() -> None:
    """T2.2 — Concurrent cold misses coalesce into 1 upstream call and survive waiter cancel."""
    seed = SeedCatalogProvider()
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def search_offers(self, intent: SearchIntent) -> CatalogSearchResult:
            self.calls += 1
            started.set()
            await release.wait()
            return await seed.search_offers(intent)

    slow = _SlowProvider()
    cache = InMemoryTTLCache()
    cached = CachedCatalogProvider(provider=slow, cache=cache, ttl_seconds=1800)
    intent = SearchIntent(query="Anker earbuds", country=CountryCode.EG, language="en")

    task1 = asyncio.create_task(cached.search_offers(intent))
    task2 = asyncio.create_task(cached.search_offers(intent))
    task3 = asyncio.create_task(cached.search_offers(intent))
    await started.wait()

    # Cancel one waiter mid-flight; remaining callers must still complete cleanly.
    task1.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task1

    release.set()
    res2, res3 = await asyncio.gather(task2, task3)
    assert slow.calls == 1
    assert len(res2.offers) >= 6
    assert res2.offers == res3.offers
    assert cached._in_flight == {}


async def test_cached_catalog_single_flight_error_cleanup() -> None:
    """T3.4 — Coalesced failures clean up _in_flight, skip caching, and allow clean retry."""
    seed = SeedCatalogProvider()
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowFlakyProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def search_offers(self, intent: SearchIntent) -> CatalogSearchResult:
            self.calls += 1
            if self.calls == 1:
                started.set()
                await release.wait()
                raise CatalogProviderError(provider="serper", retriable=True, reason="timeout")
            return await seed.search_offers(intent)

    flaky = _SlowFlakyProvider()
    cache = InMemoryTTLCache()
    cached = CachedCatalogProvider(provider=flaky, cache=cache, ttl_seconds=1800)
    intent = SearchIntent(query="Anker earbuds", country=CountryCode.SA, language="en")

    waiters = [asyncio.create_task(cached.search_offers(intent)) for _ in range(3)]
    await started.wait()
    release.set()
    results = await asyncio.gather(*waiters, return_exceptions=True)

    assert flaky.calls == 1
    assert all(isinstance(item, CatalogProviderError) for item in results)
    assert await cache.get(intent.catalog_cache_key()) is None
    assert cached._in_flight == {}

    recovered = await cached.search_offers(intent)
    assert flaky.calls == 2
    assert recovered.cache_hit is False
    assert len(recovered.offers) >= 6


async def test_cached_catalog_all_waiter_cancellation_and_distinct_key_concurrency() -> None:
    """T2.2/T3.4 — Cancelling all error waiters clears _in_flight; distinct keys run together."""
    seed = SeedCatalogProvider()
    started = asyncio.Event()
    release = asyncio.Event()

    class _BarrierFailProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def search_offers(self, intent: SearchIntent) -> CatalogSearchResult:
            self.calls += 1
            if self.calls == 1:
                started.set()
                await release.wait()
                raise CatalogProviderError(provider="serper", retriable=True, reason="timeout")
            return await seed.search_offers(intent)

    flaky = _BarrierFailProvider()
    cache = InMemoryTTLCache()
    cached = CachedCatalogProvider(provider=flaky, cache=cache, ttl_seconds=1800)
    intent_cancel = SearchIntent(query="Anker earbuds", country=CountryCode.EG, language="en")

    waiters = [asyncio.create_task(cached.search_offers(intent_cancel)) for _ in range(3)]
    await started.wait()
    for waiter in waiters:
        waiter.cancel()
    cancelled_results = await asyncio.gather(*waiters, return_exceptions=True)
    assert all(isinstance(item, asyncio.CancelledError) for item in cancelled_results)

    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert flaky.calls == 1
    assert cached._in_flight == {}
    assert await cache.get(intent_cancel.catalog_cache_key()) is None

    recovered = await cached.search_offers(intent_cancel)
    assert flaky.calls == 2
    assert recovered.cache_hit is False

    # Distinct catalog_cache_key() cold misses execute concurrently without blocking each other.
    key_a_started = asyncio.Event()
    key_a_release = asyncio.Event()

    class _DistinctKeyProvider:
        async def search_offers(self, intent: SearchIntent) -> CatalogSearchResult:
            if intent.country == CountryCode.SA:
                key_a_started.set()
                await key_a_release.wait()
            return await seed.search_offers(intent)

    concurrent_cached = CachedCatalogProvider(
        provider=_DistinctKeyProvider(),
        cache=InMemoryTTLCache(),
        ttl_seconds=600,
    )
    task_sa = asyncio.create_task(
        concurrent_cached.search_offers(
            SearchIntent(query="Anker earbuds", country=CountryCode.SA, language="en")
        )
    )
    await key_a_started.wait()
    res_ae = await concurrent_cached.search_offers(
        SearchIntent(query="Anker earbuds", country=CountryCode.AE, language="en")
    )
    assert len(res_ae.offers) >= 1
    assert not task_sa.done()
    key_a_release.set()
    res_sa = await task_sa
    assert len(res_sa.offers) >= 1
