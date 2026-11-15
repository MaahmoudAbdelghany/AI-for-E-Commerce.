"""Session repository factory providing automatic InMemorySessionStore degradation."""

import logging
from typing import Literal

from pydantic import SecretStr

from commerce_ai.adapters.session.memory import InMemorySessionStore
from commerce_ai.adapters.session.sqlalchemy_repo import (
    SQLAlchemySessionRepository,
    extract_db_password,
    sanitize_db_text,
)
from commerce_ai.config.settings import AppSettings, redact_url_password
from commerce_ai.domain.errors import SessionStoreError
from commerce_ai.domain.models import SessionState

logger = logging.getLogger(__name__)

SessionBackendName = Literal["sqlite", "postgresql", "memory"]


def _detect_backend_name(database_url: str) -> SessionBackendName | None:
    lowered = database_url.strip().lower()
    if lowered.startswith("sqlite+"):
        return "sqlite"
    if lowered.startswith("postgresql+"):
        return "postgresql"
    return None


class ResilientSessionRepository:
    """SessionRepository wrapper that fails over transparently to InMemorySessionStore."""

    def __init__(
        self,
        *,
        primary: SQLAlchemySessionRepository | None,
        fallback: InMemorySessionStore,
        primary_backend: SessionBackendName,
        redacted_url: str | None = None,
        secret_password: SecretStr | None = None,
        raw_url: str | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._redacted_url = redacted_url or "<memory>"
        self._secret_password = secret_password
        self._raw_url = raw_url
        self._is_degraded = primary is None
        self._backend_name: SessionBackendName = "memory" if primary is None else primary_backend

    @property
    def backend_name(self) -> SessionBackendName:
        """Return active backend name without exposing connection strings."""
        return self._backend_name

    @property
    def is_degraded(self) -> bool:
        """Return True when the repository has degraded to InMemorySessionStore."""
        return self._is_degraded

    def _degrade(self, operation: str, exc: Exception) -> None:
        safe_reason = sanitize_db_text(
            str(exc),
            self._secret_password,
            raw_url=self._raw_url,
        )
        if not self._is_degraded:
            logger.warning(
                "Session repository degraded to InMemorySessionStore during %s (%s): %s",
                operation,
                self._redacted_url,
                safe_reason,
            )
        self._is_degraded = True
        self._backend_name = "memory"

    async def initialize(self) -> None:
        """Initialize primary SQL storage, degrading cleanly to memory on failure."""
        if self._is_degraded or self._primary is None:
            await self._fallback.initialize()
            return
        try:
            await self._primary.initialize()
        except (SessionStoreError, OSError, TimeoutError, ValueError, RuntimeError) as exc:
            self._degrade("initialize", exc)
            await self._fallback.initialize()

    async def close(self) -> None:
        """Close both primary and fallback session stores safely."""
        if self._primary is not None:
            try:
                await self._primary.close()
            except (SessionStoreError, OSError, TimeoutError, RuntimeError) as exc:
                safe_reason = sanitize_db_text(
                    str(exc),
                    self._secret_password,
                    raw_url=self._raw_url,
                )
                logger.warning(
                    "Ignoring session repository close error (%s): %s",
                    self._redacted_url,
                    safe_reason,
                )
        await self._fallback.close()

    async def get_session(self, session_id: str) -> SessionState | None:
        """Fetch session from primary store or fall back to memory on DB failure."""
        if not self._is_degraded and self._primary is not None:
            try:
                return await self._primary.get_session(session_id)
            except (SessionStoreError, OSError, TimeoutError, RuntimeError) as exc:
                self._degrade("get_session", exc)
        return await self._fallback.get_session(session_id)

    async def save_session(self, state: SessionState, ttl_seconds: int = 86400) -> None:
        """Persist session to primary store or fall back to memory on DB failure."""
        if not self._is_degraded and self._primary is not None:
            try:
                await self._primary.save_session(state, ttl_seconds=ttl_seconds)
                return
            except (SessionStoreError, OSError, TimeoutError, RuntimeError) as exc:
                self._degrade("save_session", exc)
        await self._fallback.save_session(state, ttl_seconds=ttl_seconds)

    async def delete_session(self, session_id: str) -> None:
        """Delete session from primary store or fall back to memory on DB failure."""
        if not self._is_degraded and self._primary is not None:
            try:
                await self._primary.delete_session(session_id)
                return
            except (SessionStoreError, OSError, TimeoutError, RuntimeError) as exc:
                self._degrade("delete_session", exc)
        await self._fallback.delete_session(session_id)


def create_session_repository(settings: AppSettings) -> ResilientSessionRepository:
    """Synchronously construct a ResilientSessionRepository from AppSettings."""
    fallback = InMemorySessionStore(max_turns=settings.session_max_turns)
    raw_url = getattr(settings, "database_url", "")
    if not isinstance(raw_url, str) or not raw_url.strip():
        logger.warning("Empty database_url provided; degrading session store to memory")
        return ResilientSessionRepository(
            primary=None,
            fallback=fallback,
            primary_backend="memory",
        )

    redacted = redact_url_password(raw_url) or "<redacted>"
    secret_password = extract_db_password(raw_url)
    detected_backend = _detect_backend_name(raw_url)

    try:
        primary = SQLAlchemySessionRepository(
            database_url=raw_url,
            max_turns=settings.session_max_turns,
        )
    except (SessionStoreError, ValueError, OSError) as exc:
        safe_reason = sanitize_db_text(str(exc), secret_password, raw_url=raw_url)
        logger.warning(
            "Unable to configure SQL session repository (%s); degrading to memory: %s",
            redacted,
            safe_reason,
        )
        return ResilientSessionRepository(
            primary=None,
            fallback=fallback,
            primary_backend="memory",
            redacted_url=redacted,
            secret_password=secret_password,
            raw_url=raw_url,
        )

    return ResilientSessionRepository(
        primary=primary,
        fallback=fallback,
        primary_backend=detected_backend or "sqlite",
        redacted_url=redacted,
        secret_password=secret_password,
        raw_url=raw_url,
    )
