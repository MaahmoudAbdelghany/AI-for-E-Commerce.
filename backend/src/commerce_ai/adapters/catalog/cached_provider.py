"""Resilient TTL caching decorator wrapping any CatalogProvider."""

import logging

from pydantic import ValidationError

from commerce_ai.domain.errors import CacheStoreError
from commerce_ai.domain.models import CatalogSearchResult, SearchIntent
from commerce_ai.domain.ports import CacheStore, CatalogProvider

logger = logging.getLogger(__name__)


class CachedCatalogProvider:
    """CatalogProvider decorator reading and writing normalized SearchIntent cache keys."""

    def __init__(
        self,
        provider: CatalogProvider,
        cache: CacheStore,
        ttl_seconds: int = 1800,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    async def search_offers(self, intent: SearchIntent) -> CatalogSearchResult:
        """Serve cached CatalogSearchResult on hit or delegate on miss/cache error."""
        cache_key = intent.normalized_cache_key()

        try:
            cached_raw = await self._cache.get(cache_key)
        except CacheStoreError as exc:
            logger.warning("Cache read error for key %s; bypassing cache: %s", cache_key, exc)
            cached_raw = None

        if cached_raw is not None:
            try:
                cached_result = CatalogSearchResult.model_validate_json(cached_raw)
                return cached_result.model_copy(update={"cache_hit": True})
            except (ValidationError, ValueError) as exc:
                logger.warning(
                    "Corrupt cache entry for key %s; bypassing cache: %s",
                    cache_key,
                    exc,
                )

        result = await self._provider.search_offers(intent)
        normalized_result = result.model_copy(update={"cache_hit": False})

        try:
            await self._cache.set(
                cache_key,
                normalized_result.model_dump_json(),
                self._ttl_seconds,
            )
        except CacheStoreError as exc:
            logger.warning(
                "Cache write error for key %s; returning fresh result: %s", cache_key, exc
            )

        return normalized_result
