"""In-process asynchronous session store with bounded LRU eviction and monotonic TTL."""

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable

from commerce_ai.domain.models import SessionState


class InMemorySessionStore:
    """Coroutine-safe bounded LRU SessionRepository with monotonic TTL expiry."""

    def __init__(
        self,
        clock: Callable[[], float] | None = None,
        max_sessions: int = 1024,
        max_turns: int = 10,
    ) -> None:
        if max_sessions <= 0:
            raise ValueError("max_sessions must be positive")
        if max_turns < 2:
            raise ValueError("max_turns must be at least 2")
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._max_sessions = max_sessions
        self._max_turns = max_turns
        self._entries: OrderedDict[str, tuple[SessionState, float]] = OrderedDict()
        self._lock = asyncio.Lock()

    def _clone_state(self, state: SessionState, *, trim_turns: bool = False) -> SessionState:
        source_turns = state.turns[-self._max_turns :] if trim_turns else state.turns
        return state.model_copy(
            deep=True,
            update={
                "last_intent": (
                    state.last_intent.model_copy(deep=True)
                    if state.last_intent is not None
                    else None
                ),
                "last_ranked_offers": [
                    offer.model_copy(deep=True) for offer in state.last_ranked_offers
                ],
                "turns": [turn.model_copy(deep=True) for turn in source_turns],
            },
        )

    def _prune_expired_locked(self, now: float) -> None:
        expired_keys = [
            session_id for session_id, (_, expires_at) in self._entries.items() if now >= expires_at
        ]
        for session_id in expired_keys:
            del self._entries[session_id]

    async def initialize(self) -> None:
        """No-op lifecycle hook matching SQLAlchemySessionRepository."""
        return None

    async def close(self) -> None:
        """No-op lifecycle hook matching SQLAlchemySessionRepository."""
        return None

    async def get_session(self, session_id: str) -> SessionState | None:
        """Return a defensive copy of an active session, refreshing LRU recency."""
        async with self._lock:
            entry = self._entries.get(session_id)
            if entry is None:
                return None
            stored_state, expires_at = entry
            if self._clock() >= expires_at:
                del self._entries[session_id]
                return None
            self._entries.move_to_end(session_id)
            return self._clone_state(stored_state)

    async def save_session(self, state: SessionState, ttl_seconds: int = 86400) -> None:
        """Store trimmed session state with positive TTL; prune expired before LRU eviction."""
        async with self._lock:
            session_id = state.session_id
            if ttl_seconds <= 0:
                self._entries.pop(session_id, None)
                return

            now = self._clock()
            expires_at = now + float(ttl_seconds)
            stored_copy = self._clone_state(state, trim_turns=True)

            if session_id in self._entries:
                self._entries[session_id] = (stored_copy, expires_at)
                self._entries.move_to_end(session_id)
                return

            if len(self._entries) >= self._max_sessions:
                self._prune_expired_locked(now)
                while len(self._entries) >= self._max_sessions:
                    self._entries.popitem(last=False)

            self._entries[session_id] = (stored_copy, expires_at)

    async def delete_session(self, session_id: str) -> None:
        """Idempotently remove a session entry if present."""
        async with self._lock:
            self._entries.pop(session_id, None)
