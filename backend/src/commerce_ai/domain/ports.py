"""Pure hexagonal domain ports for catalog, cache, LLM, and session persistence."""

from typing import Protocol, runtime_checkable

from commerce_ai.domain.models import (
    CatalogSearchResult,
    LLMRequest,
    LLMResponse,
    SearchIntent,
    SessionState,
)


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


@runtime_checkable
class LLMClient(Protocol):
    """Abstract asynchronous LLM completion port."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute a bounded completion request and return a typed response."""
        ...


@runtime_checkable
class SessionRepository(Protocol):
    """Abstract asynchronous conversational session storage port."""

    async def get_session(self, session_id: str) -> SessionState | None:
        """Retrieve an active session state, or None if absent or expired."""
        ...

    async def save_session(self, state: SessionState, ttl_seconds: int = 86400) -> None:
        """Persist or update session state with the requested TTL in seconds."""
        ...

    async def delete_session(self, session_id: str) -> None:
        """Delete a session by identifier if present."""
        ...
