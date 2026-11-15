"""Async SQLAlchemy 2.0 session repository supporting SQLite and PostgreSQL."""

import re
import time
from collections.abc import Callable
from urllib.parse import quote, unquote, urlsplit

from pydantic import SecretStr, ValidationError
from sqlalchemy import Float, String, Text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from commerce_ai.config.settings import redact_url_password
from commerce_ai.domain.errors import SessionStoreError
from commerce_ai.domain.models import SessionState

_URL_CREDENTIALS_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:/?#\s]*):([^\s/?#]+)@")
_QUERY_SECRET_RE = re.compile(r"([?&](?:password|pass|token)=)([^&#\s]+)", re.IGNORECASE)
_PASSWORD_KWARG_RE = re.compile(
    r"((?:password|passwd|pass|token)\s*=\s*['\"]?)([^'\",\s\)]+)(['\"]?)",
    re.IGNORECASE,
)
_SUPPORTED_DRIVERS = frozenset({"sqlite+aiosqlite", "postgresql+asyncpg"})


def extract_db_password(database_url: str | None) -> SecretStr | None:
    """Extract an optional URL password wrapped in SecretStr without exposing raw text."""
    if not database_url:
        return None
    raw_password: str | None = None
    try:
        parsed = urlsplit(database_url)
        raw_password = parsed.password
        _ = parsed.username
        _ = parsed.hostname
        _ = parsed.port
        _ = parsed.query
    except ValueError:
        match = _URL_CREDENTIALS_RE.search(database_url)
        if match is not None:
            raw_password = match.group(2)
    if not raw_password:
        return None
    decoded = unquote(raw_password)
    return SecretStr(decoded) if decoded else None


def sanitize_db_text(
    text: str,
    secret_password: SecretStr | None = None,
    *,
    raw_url: str | None = None,
) -> str:
    """Strip any database URL credentials, query secrets, or password arguments from text."""
    sanitized = text
    if raw_url:
        redacted_url = redact_url_password(raw_url)
        if redacted_url:
            sanitized = sanitized.replace(raw_url, redacted_url)
    sanitized = _URL_CREDENTIALS_RE.sub(r"\1:***@", sanitized)
    sanitized = _QUERY_SECRET_RE.sub(r"\1***", sanitized)
    sanitized = _PASSWORD_KWARG_RE.sub(r"\1***\3", sanitized)
    if secret_password is not None:
        raw_secret = secret_password.get_secret_value()
        if raw_secret:
            sanitized = sanitized.replace(raw_secret, "***")
            encoded_secret = quote(raw_secret, safe="")
            if encoded_secret != raw_secret:
                sanitized = sanitized.replace(encoded_secret, "***")
    return sanitized


class Base(DeclarativeBase):
    """Declarative ORM base for Feature 2.2 async session storage."""


class CommerceSessionRow(Base):
    """Persisted shopping session row inside the `commerce_sessions` table."""

    __tablename__ = "commerce_sessions"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at_epoch: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    updated_at_epoch: Mapped[float] = mapped_column(Float, nullable=False)


class SQLAlchemySessionRepository:
    """Async SQLAlchemy 2.0 SessionRepository backed by sqlite+aiosqlite or postgresql+asyncpg."""

    def __init__(
        self,
        database_url: str,
        max_turns: int = 10,
        echo: bool = False,
        wall_clock: Callable[[], float] | None = None,
    ) -> None:
        if max_turns < 2:
            raise ValueError("max_turns must be at least 2")
        if not database_url or not database_url.strip():
            raise SessionStoreError("Database URL must not be empty")

        self._raw_url = database_url
        self._redacted_url: str = redact_url_password(database_url) or "<redacted>"
        self._secret_password: SecretStr | None = extract_db_password(database_url)
        self._max_turns = max_turns
        self._clock: Callable[[], float] = wall_clock if wall_clock is not None else time.time

        try:
            parsed_url = make_url(database_url)
        except (ArgumentError, SQLAlchemyError, ValueError) as exc:
            sanitized = sanitize_db_text(str(exc), self._secret_password, raw_url=database_url)
            raise SessionStoreError(
                f"Invalid database URL {self._redacted_url}: {sanitized}"
            ) from exc

        if parsed_url.drivername not in _SUPPORTED_DRIVERS:
            raise SessionStoreError(
                f"Unsupported database driver {parsed_url.drivername!r} for {self._redacted_url}"
            )

        is_memory_sqlite = parsed_url.drivername == "sqlite+aiosqlite" and parsed_url.database in (
            None,
            "",
            ":memory:",
        )

        try:
            if is_memory_sqlite:
                self._engine: AsyncEngine = create_async_engine(
                    database_url,
                    echo=echo,
                    poolclass=StaticPool,
                )
            else:
                self._engine = create_async_engine(
                    database_url,
                    echo=echo,
                    pool_pre_ping=True,
                )
        except (SQLAlchemyError, ValueError, OSError, ImportError) as exc:
            sanitized = sanitize_db_text(str(exc), self._secret_password, raw_url=database_url)
            raise SessionStoreError(
                f"Failed to create database engine for {self._redacted_url}: {sanitized}"
            ) from exc

        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
        )

    def _wrap_error(self, operation: str, exc: Exception) -> SessionStoreError:
        sanitized = sanitize_db_text(str(exc), self._secret_password, raw_url=self._raw_url)
        return SessionStoreError(
            f"Session store {operation} failed ({self._redacted_url}): {sanitized}"
        )

    async def initialize(self) -> None:
        """Idempotently create the `commerce_sessions` table via Base.metadata.create_all."""
        try:
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except (SQLAlchemyError, OSError, TimeoutError, ValueError, RuntimeError) as exc:
            raise self._wrap_error("initialize", exc) from exc

    async def close(self) -> None:
        """Dispose the underlying async engine and connection pool."""
        try:
            await self._engine.dispose()
        except (SQLAlchemyError, OSError, TimeoutError, RuntimeError) as exc:
            raise self._wrap_error("close", exc) from exc

    async def get_session(self, session_id: str) -> SessionState | None:
        """Fetch an active session from SQL storage, deleting and skipping expired rows."""
        try:
            async with self._session_factory() as session:
                row = await session.get(CommerceSessionRow, session_id)
                if row is None:
                    return None
                if self._clock() >= row.expires_at_epoch:
                    await session.delete(row)
                    await session.commit()
                    return None
                payload_json = row.payload_json
        except (SQLAlchemyError, OSError, TimeoutError, RuntimeError) as exc:
            raise self._wrap_error("get_session", exc) from exc

        try:
            return SessionState.model_validate_json(
                payload_json,
                context={"allow_verified_google_shopping_from_cache": True},
            )
        except (ValidationError, ValueError) as exc:
            raise SessionStoreError(
                f"Corrupt session payload for {session_id!r} ({self._redacted_url})"
            ) from exc

    async def save_session(self, state: SessionState, ttl_seconds: int = 86400) -> None:
        """Upsert trimmed session state with positive TTL; non-positive TTL removes the row."""
        if ttl_seconds <= 0:
            await self.delete_session(state.session_id)
            return

        now = self._clock()
        expires_at = now + float(ttl_seconds)
        trimmed_turns = list(state.turns[-self._max_turns :])
        stored_state = state.model_copy(update={"turns": trimmed_turns})
        payload_json = stored_state.model_dump_json()

        try:
            async with self._session_factory() as session:
                await session.merge(
                    CommerceSessionRow(
                        session_id=stored_state.session_id,
                        market=stored_state.market.value,
                        payload_json=payload_json,
                        expires_at_epoch=expires_at,
                        updated_at_epoch=now,
                    )
                )
                await session.commit()
        except (SQLAlchemyError, OSError, TimeoutError, RuntimeError) as exc:
            raise self._wrap_error("save_session", exc) from exc

    async def delete_session(self, session_id: str) -> None:
        """Idempotently delete a persisted session row if it exists."""
        try:
            async with self._session_factory() as session:
                row = await session.get(CommerceSessionRow, session_id)
                if row is not None:
                    await session.delete(row)
                    await session.commit()
        except (SQLAlchemyError, OSError, TimeoutError, RuntimeError) as exc:
            raise self._wrap_error("delete_session", exc) from exc
