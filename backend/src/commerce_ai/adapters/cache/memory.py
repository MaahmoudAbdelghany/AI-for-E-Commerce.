"""In-process asynchronous TTL cache store using a monotonic clock."""

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable


class InMemoryTTLCache:
    """Thread/coroutine-safe bounded LRU in-memory CacheStore with monotonic TTL expiry."""

    def __init__(
        self,
        clock: Callable[[], float] | None = None,
        max_entries: int = 1024,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._max_entries: int = max_entries
        self._entries: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock = asyncio.Lock()

    def _prune_expired_locked(self, now: float) -> None:
        expired_keys = [k for k, (_, expires_at) in self._entries.items() if now >= expires_at]
        for expired_key in expired_keys:
            del self._entries[expired_key]

    async def get(self, key: str) -> str | None:
        """Return the cached value if present and unexpired; lazily evict expired entries."""
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if self._clock() >= expires_at:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store value with positive TTL seconds; prune expired and evict LRU at capacity."""
        async with self._lock:
            if ttl_seconds <= 0:
                self._entries.pop(key, None)
                return
            now = self._clock()
            expires_at = now + float(ttl_seconds)
            if key in self._entries:
                self._entries[key] = (value, expires_at)
                self._entries.move_to_end(key)
                return
            if len(self._entries) >= self._max_entries:
                self._prune_expired_locked(now)
                while len(self._entries) >= self._max_entries:
                    self._entries.popitem(last=False)
            self._entries[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        """Idempotently delete a cached key if it exists."""
        async with self._lock:
            self._entries.pop(key, None)
