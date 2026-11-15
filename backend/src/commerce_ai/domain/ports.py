"""Pure hexagonal domain ports for catalog retrieval and TTL caching."""

from typing import Protocol, runtime_checkable

from commerce_ai.domain.models import CatalogSearchResult, SearchIntent


@runtime_checkable
class CatalogProvider(Protocol):
    """Abstract marketplace catalog retrieval port."""

    async def search_offers(self, intent: SearchIntent) -> CatalogSearchResult:
        """Fetch grounded marketplace offers matching the given search intent."""
        ...


@runtime_checkable
class CacheStore(Protocol):
    """Abstract asynchronous key-value TTL cache port."""

    async def get(self, key: str) -> str | None:
        """Retrieve cached string value for key, or None if missing or expired."""
        ...

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store string value under key for ttl_seconds."""
        ...

    async def delete(self, key: str) -> None:
        """Remove cached key if present without raising on missing keys."""
        ...
