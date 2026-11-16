"""End-to-end Phase 1 offline integration tests across EG, SA, and AE (PI.1)."""

from decimal import Decimal
from typing import Literal

import fakeredis.aioredis
import pytest

from commerce_ai.adapters.cache import redis_store as redis_store_module
from commerce_ai.adapters.cache.factory import create_cache_store
from commerce_ai.adapters.cache.memory import InMemoryTTLCache
from commerce_ai.adapters.cache.redis_store import RedisCacheStore
from commerce_ai.adapters.catalog.cached_provider import CachedCatalogProvider
from commerce_ai.adapters.catalog.factory import create_catalog_provider
from commerce_ai.adapters.catalog.seed_provider import SeedCatalogProvider
from commerce_ai.config.markets import MARKET_REGISTRY
from commerce_ai.config.scoring import ScoringConfig
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.models import (
    CatalogSearchResult,
    CatalogSourceMode,
    CountryCode,
    SearchIntent,
    StoreFilter,
)
from commerce_ai.domain.ports import CacheStore, CatalogProvider
from commerce_ai.domain.ranking import rank_top_offers


class _SpyCatalogProvider:
    """Call-counting spy wrapper verifying zero repeat upstream calls on cache hits."""

    def __init__(self, inner: CatalogProvider) -> None:
        self._inner = inner
        self.call_count = 0

    async def search_offers(self, intent: SearchIntent) -> CatalogSearchResult:
        self.call_count += 1
        return await self._inner.search_offers(intent)


def _create_cache_backend(
    backend_kind: Literal["memory", "redis"],
) -> tuple[CacheStore, fakeredis.aioredis.FakeRedis | None]:
    if backend_kind == "memory":
        return InMemoryTTLCache(), None
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return RedisCacheStore(client=fake_redis), fake_redis


@pytest.mark.parametrize("country", [CountryCode.EG, CountryCode.SA, CountryCode.AE])
@pytest.mark.parametrize("cache_backend", ["memory", "redis"])
@pytest.mark.parametrize(
    ("language", "initial_query", "repeat_query"),
    [
        ("en", "Anker earbuds", "  anker   EARBUDS! "),
        ("ar", "سماعة أنكر", "  سَمَاعَةُ   أنْكَر! "),
    ],
)
async def test_phase1_e2e_bilingual_traps_and_cache_across_markets(
    country: CountryCode,
    cache_backend: Literal["memory", "redis"],
    language: Literal["ar", "en"],
    initial_query: str,
    repeat_query: str,
) -> None:
    """PI.1 — Seed -> Cached (InMemory & fakeredis) -> rank_top_offers across EG/SA/AE."""
    spy = _SpyCatalogProvider(SeedCatalogProvider())
    cache_store, fake_redis = _create_cache_backend(cache_backend)
    try:
        provider = CachedCatalogProvider(provider=spy, cache=cache_store, ttl_seconds=1800)
        intent = SearchIntent(
            query=initial_query,
            country=country,
            store=StoreFilter.BOTH,
            language=language,
        )

        # First lookup: cache miss hits SeedCatalogProvider once.
        miss_result = await provider.search_offers(intent)
        assert spy.call_count == 1
        assert miss_result.cache_hit is False
        assert miss_result.source_mode == CatalogSourceMode.SEED
        assert len(miss_result.offers) == 7

        expected_currency = MARKET_REGISTRY[country].currency
        assert all(offer.country == country for offer in miss_result.offers)
        assert all(offer.currency == expected_currency for offer in miss_result.offers)

        if fake_redis is not None:
            ttl = await fake_redis.ttl(intent.catalog_cache_key())
            assert 0 < ttl <= 1800

        # Repeat normalized query: cache hit with zero repeat upstream provider calls.
        repeat_intent = SearchIntent(
            query=repeat_query,
            country=country,
            store=StoreFilter.BOTH,
            language=language,
        )
        hit_result = await provider.search_offers(repeat_intent)
        assert spy.call_count == 1
        assert hit_result.cache_hit is True
        assert hit_result.source_mode == CatalogSourceMode.SEED
        assert hit_result.offers == miss_result.offers

        # Deterministic ranking guards against accessory, 4x scalper, 5.0/1-rev, and unrated traps.
        ranking_miss = rank_top_offers(miss_result.offers, intent)
        ranking_hit = rank_top_offers(hit_result.offers, repeat_intent)
        assert ranking_hit == ranking_miss

        assert ranking_miss.total_candidates == 7
        assert ranking_miss.filtered_accessories_count == 1
        assert ranking_miss.filtered_outliers_count == 1
        assert ranking_miss.degraded_fewer_than_k is False
        assert len(ranking_miss.ranked_offers) == 3

        ranked = ranking_miss.ranked_offers
        assert [item.rank for item in ranked] == [1, 2, 3]
        assert ranked[0].value_score > ranked[1].value_score > ranked[2].value_score

        ranked_ids = [item.offer.offer_id for item in ranked]
        prefix = country.value.lower()
        assert f"{prefix}-noon-anker-case-trap" not in ranked_ids
        assert f"{prefix}-amazon-anker-scalper-trap" not in ranked_ids

        # Proven well-reviewed offer (#1) beats unrated fallback (#2) and 5.0/1-rev trap (#3).
        assert ranked_ids == [
            f"{prefix}-amazon-anker-r50i",
            f"{prefix}-amazon-anker-unrated-trap",
            f"{prefix}-noon-anker-5star-1rev-trap",
        ]
        assert ranked[0].bayesian_rating > 4.5
        assert "high_review_confidence" in ranked[0].match_reasons

        assert ranked[1].offer.rating is None
        assert ranked[1].offer.review_count == 0
        assert ranked[1].bayesian_rating == pytest.approx(3.4)
        assert "unrated_fallback" in ranked[1].match_reasons

        assert ranked[2].offer.rating == 5.0
        assert ranked[2].offer.review_count == 1
        assert ranked[2].bayesian_rating < 4.1
    finally:
        if fake_redis is not None:
            await fake_redis.aclose()


@pytest.mark.parametrize("country", [CountryCode.EG, CountryCode.SA, CountryCode.AE])
async def test_phase1_e2e_additional_categories_and_intent_filters(
    country: CountryCode,
) -> None:
    """PI.1 — Bilingual category flows, min_rating unrated exclusion, and accessory opt-in."""
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    settings = AppSettings(
        _env_file=None,
        catalog_mode="auto",
        serper_api_key=None,
        cache_ttl_seconds=900,
    )
    try:
        cache_store = await create_cache_store(settings, redis_client=fake_redis)
        assert isinstance(cache_store, RedisCacheStore)

        spy = _SpyCatalogProvider(SeedCatalogProvider())
        provider = CachedCatalogProvider(
            provider=spy,
            cache=cache_store,
            ttl_seconds=settings.cache_ttl_seconds,
        )
        prefix = country.value.lower()

        # 1. Smartphones (bilingual): rejects screen protector trap; single survivor has P_norm=1.0.
        phone_queries: tuple[tuple[Literal["ar", "en"], str, str], ...] = (
            ("en", "iPhone 15", "  IPHONE  15! "),
            ("ar", "آيفون 15", "  آيفُون   15؟ "),
        )
        for lang, q1, q2 in phone_queries:
            intent = SearchIntent(query=q1, country=country, language=lang)
            miss = await provider.search_offers(intent)
            hit = await provider.search_offers(
                SearchIntent(query=q2, country=country, language=lang)
            )
            assert miss.cache_hit is False
            assert hit.cache_hit is True
            assert hit.offers == miss.offers

            ranked_phones = rank_top_offers(hit.offers, intent)
            assert ranked_phones.filtered_accessories_count == 1
            assert ranked_phones.degraded_fewer_than_k is True
            assert all(
                not item.offer.offer_id.endswith("protector-trap")
                for item in ranked_phones.ranked_offers
            )
            if country in (CountryCode.SA, CountryCode.AE):
                assert len(ranked_phones.ranked_offers) == 1
                assert ranked_phones.ranked_offers[0].price_norm == 1.0
            else:
                assert len(ranked_phones.ranked_offers) == 2

        # 2. Smartwatches (Arabic): rejects watch strap trap and ranks 2 smartwatches.
        watch_intent = SearchIntent(query="ساعة ذكية", country=country, language="ar")
        watch_miss = await provider.search_offers(watch_intent)
        watch_hit = await provider.search_offers(
            SearchIntent(query="  سَاعَةُ   ذَكِيَّة! ", country=country, language="ar")
        )
        assert watch_miss.cache_hit is False
        assert watch_hit.cache_hit is True
        ranked_watches = rank_top_offers(watch_hit.offers, watch_intent)
        assert ranked_watches.filtered_accessories_count == 1
        assert ranked_watches.degraded_fewer_than_k is True
        assert len(ranked_watches.ranked_offers) == 2
        assert f"{prefix}-amazon-watch-strap-trap" not in [
            item.offer.offer_id for item in ranked_watches.ranked_offers
        ]

        # 3. min_rating excludes unrated offers per P3 while keeping r50i #1 above 5-star/1-rev.
        rated_only_intent = SearchIntent(
            query="Anker earbuds",
            country=country,
            min_rating=4.0,
            language="en",
        )
        rated_catalog = await provider.search_offers(rated_only_intent)
        assert rated_catalog.cache_hit is False
        rated_ranking = rank_top_offers(rated_catalog.offers, rated_only_intent)
        assert rated_ranking.filtered_accessories_count == 1
        assert rated_ranking.filtered_outliers_count == 1
        rated_ids = [item.offer.offer_id for item in rated_ranking.ranked_offers]
        assert f"{prefix}-amazon-anker-unrated-trap" not in rated_ids
        assert rated_ids == [
            f"{prefix}-amazon-anker-r50i",
            f"{prefix}-noon-anker-5star-1rev-trap",
            f"{prefix}-noon-anker-l4nc",
        ]

        # 4. Positive bilingual accessory searches (include_accessories=False) retain case trap.
        for acc_lang, acc_query in (("en", "Anker earbuds case"), ("ar", "جراب أنكر")):
            pos_acc_intent = SearchIntent(
                query=acc_query,
                country=country,
                include_accessories=False,
                language=acc_lang,  # type: ignore[arg-type]
            )
            pos_acc_catalog = await provider.search_offers(pos_acc_intent)
            pos_acc_ranking = rank_top_offers(pos_acc_catalog.offers, pos_acc_intent)
            assert pos_acc_ranking.filtered_accessories_count == 0
            assert f"{prefix}-noon-anker-case-trap" in [
                item.offer.offer_id for item in pos_acc_ranking.ranked_offers
            ]

        # 5. Explicit include_accessories=True bypasses Stage 1 without accessory keyword in query.
        accessory_opt_in_intent = SearchIntent(
            query="Anker earbuds",
            country=country,
            include_accessories=True,
            language="en",
        )
        acc_catalog = await provider.search_offers(accessory_opt_in_intent)
        acc_ranking = rank_top_offers(acc_catalog.offers, accessory_opt_in_intent)
        assert acc_ranking.filtered_accessories_count == 0
        assert acc_ranking.filtered_outliers_count == 2
        no_outlier_acc_ranking = rank_top_offers(
            acc_catalog.offers,
            accessory_opt_in_intent,
            config=ScoringConfig(min_candidates_for_outlier_guard=99),
        )
        assert no_outlier_acc_ranking.filtered_accessories_count == 0
        assert any(
            item.offer.offer_id == f"{prefix}-noon-anker-case-trap"
            for item in no_outlier_acc_ranking.ranked_offers
        )

        # 6. Home appliances (bilingual air fryer E2E).
        appliance_queries: tuple[tuple[Literal["ar", "en"], str], ...] = (
            ("en", "air fryer"),
            ("ar", "قلاية هوائية"),
        )
        for app_lang, app_query in appliance_queries:
            app_intent = SearchIntent(query=app_query, country=country, language=app_lang)
            app_catalog = await provider.search_offers(app_intent)
            app_ranking = rank_top_offers(app_catalog.offers, app_intent)
            assert app_ranking.filtered_accessories_count == 0
            assert app_ranking.filtered_outliers_count == 0
            assert app_ranking.degraded_fewer_than_k is True
            assert {item.offer.offer_id for item in app_ranking.ranked_offers} == {
                f"{prefix}-amazon-philips-airfryer",
                f"{prefix}-noon-ninja-airfryer",
            }

        # Expect 8 upstream misses: accessory_opt_in_intent reuses the cached "Anker earbuds"
        # catalog entry from rated_only_intent via SearchIntent.catalog_cache_key().
        assert acc_catalog.cache_hit is True
        assert spy.call_count == 8
    finally:
        await fake_redis.aclose()


async def test_phase1_e2e_factory_fallback_and_cross_market_key_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PI.1 — Factory wiring with unreachable Redis falls back cleanly and isolates markets."""
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
        cache_ttl_seconds=600,
    )
    cache_store = await create_cache_store(settings, ping_timeout_seconds=0.1)
    assert isinstance(cache_store, InMemoryTTLCache)

    provider = create_catalog_provider(settings, cache=cache_store)
    assert isinstance(provider, CachedCatalogProvider)

    seen_keys: set[str] = set()
    for country in (CountryCode.EG, CountryCode.SA, CountryCode.AE):
        intent = SearchIntent(
            query="لابتوب",
            country=country,
            max_budget=Decimal("100000.00"),
            language="ar",
        )
        seen_keys.add(intent.catalog_cache_key())

        miss = await provider.search_offers(intent)
        assert miss.cache_hit is False
        assert miss.source_mode == CatalogSourceMode.SEED

        hit = await provider.search_offers(
            SearchIntent(
                query="  لَابْتُوب! ",
                country=country,
                max_budget=Decimal("100000.00"),
                language="ar",
            )
        )
        assert hit.cache_hit is True
        assert hit.offers == miss.offers

        ranked = rank_top_offers(hit.offers, intent)
        assert ranked.filtered_accessories_count == 1
        assert ranked.filtered_outliers_count == 0
        assert len(ranked.ranked_offers) == 2
        assert ranked.ranked_offers[0].value_score >= ranked.ranked_offers[1].value_score
        expected_currency = MARKET_REGISTRY[country].currency
        assert all(
            item.offer.country == country and item.offer.currency == expected_currency
            for item in ranked.ranked_offers
        )

    assert len(seen_keys) == 3
