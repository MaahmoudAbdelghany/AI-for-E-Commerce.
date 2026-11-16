"""Resilient TTL caching decorator with single-flight coalescing wrapping CatalogProvider."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from pydantic import ValidationError

from commerce_ai.domain.errors import CacheStoreError
from commerce_ai.domain.models import CatalogSearchResult, SearchIntent
from commerce_ai.domain.ports import CacheStore, CatalogProvider

logger = logging.getLogger(__name__)


@dataclass
class _KeyLockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    waiters: int = 0


def _consume_unretrieved_exception(task: asyncio.Task[CatalogSearchResult]) -> None:
    """Prevent unretrieved-exception warnings when all shielded waiters cancel early."""
    if not task.cancelled():
        _ = task.exception()


class CachedCatalogProvider:
    """CatalogProvider decorator reading and writing catalog_cache_key() with single-flight."""

    def __init__(
        self,
        provider: CatalogProvider,
        cache: CacheStore,
        ttl_seconds: int = 1800,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._key_locks: dict[str, _KeyLockEntry] = {}
        self._in_flight: dict[str, asyncio.Task[CatalogSearchResult]] = {}

    @asynccontextmanager
    async def _use_key_lock(self, cache_key: str) -> AsyncIterator[None]:
        async with self._lock:
            entry = self._key_locks.get(cache_key)
            if entry is None:
                entry = _KeyLockEntry()
                self._key_locks[cache_key] = entry
            entry.waiters += 1
        try:
            async with entry.lock:
                yield
        finally:
            async with self._lock:
                current = self._key_locks.get(cache_key)
                if current is entry:
                    entry.waiters -= 1
                    if entry.waiters <= 0:
                        del self._key_locks[cache_key]

    async def _read_cached_result(self, cache_key: str) -> CatalogSearchResult | None:
        try:
            cached_raw = await self._cache.get(cache_key)
        except CacheStoreError as exc:
            logger.warning("Cache read error for key %s; bypassing cache: %s", cache_key, exc)
            return None

        if cached_raw is None:
            return None

        try:
            cached_result = CatalogSearchResult.model_validate_json(
                cached_raw,
                context={"allow_verified_google_shopping_from_cache": True},
            )
            return cached_result.model_copy(update={"cache_hit": True})
        except (ValidationError, ValueError) as exc:
            logger.warning(
                "Corrupt cache entry for key %s; bypassing cache: %s",
                cache_key,
                exc,
            )
            return None

    async def _fetch_and_cache(
        self,
        cache_key: str,
        intent: SearchIntent,
    ) -> CatalogSearchResult:
        try:
            result = await self._provider.search_offers(intent)
            normalized_result = result.model_copy(update={"cache_hit": False})

            async with self._use_key_lock(cache_key):
                try:
                    await self._cache.set(
                        cache_key,
                        normalized_result.model_dump_json(),
                        self._ttl_seconds,
                    )
                except CacheStoreError as exc:
                    logger.warning(
                        "Cache write error for key %s; returning fresh result: %s",
                        cache_key,
                        exc,
                    )
                current_task = asyncio.current_task()
                if self._in_flight.get(cache_key) is current_task:
                    self._in_flight.pop(cache_key, None)

            return normalized_result
        finally:
            current_task = asyncio.current_task()
            if self._in_flight.get(cache_key) is current_task:
                async with self._use_key_lock(cache_key):
                    if self._in_flight.get(cache_key) is current_task:
                        self._in_flight.pop(cache_key, None)

    async def search_offers(self, intent: SearchIntent) -> CatalogSearchResult:
        """Serve cached CatalogSearchResult on hit or coalesce concurrent cold misses."""
        cache_key = intent.catalog_cache_key()

        async with self._use_key_lock(cache_key):
            cached_result = await self._read_cached_result(cache_key)
            if cached_result is not None:
                return cached_result

            task = self._in_flight.get(cache_key)
            if task is None:
                task = asyncio.create_task(self._fetch_and_cache(cache_key, intent))
                task.add_done_callback(_consume_unretrieved_exception)
                self._in_flight[cache_key] = task

        result = await asyncio.shield(task)
        return result.model_copy(update={"offers": list(result.offers)})
