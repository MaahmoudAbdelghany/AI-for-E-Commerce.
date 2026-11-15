"""In-process asynchronous TTL cache store using a monotonic clock."""

import asyncio
import time
from collections.abc import Callable


class InMemoryTTLCache:
    """Thread/coroutine-safe in-memory CacheStore implementation with monotonic TTL expiry."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._entries: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

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
            return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store value with positive TTL seconds; non-positive TTL purges any stale key."""
        async with self._lock:
            if ttl_seconds <= 0:
                self._entries.pop(key, None)
                return
            self._entries[key] = (value, self._clock() + float(ttl_seconds))

    async def delete(self, key: str) -> None:
        """Idempotently delete a cached key if it exists."""
        async with self._lock:
            self._entries.pop(key, None)
