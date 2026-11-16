"""Offline unit and error-handling tests for async session persistence and fallback."""

import asyncio
import logging
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from commerce_ai.adapters.session.factory import (
    ResilientSessionRepository,
    create_session_repository,
)
from commerce_ai.adapters.session.memory import InMemorySessionStore
from commerce_ai.adapters.session.sqlalchemy_repo import (
    SessionDataError,
    SQLAlchemySessionRepository,
)
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.errors import SessionStoreError
from commerce_ai.domain.models import (
    CountryCode,
    CurrencyCode,
    ProductOffer,
    RankedOffer,
    SearchIntent,
    SessionState,
    SessionTurn,
    StoreId,
    TurnAction,
)
from commerce_ai.domain.ports import SessionRepository


class _FakeClock:
    def __init__(self, initial: float = 1000.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, delta: float) -> None:
        self.now += delta


def _make_turn(idx: int, *, role: str = "user") -> SessionTurn:
    typed_role: str = "user" if role == "user" else "assistant"
    return SessionTurn(
        role=typed_role,  # type: ignore[arg-type]
        content=f"turn-{idx}",
        action=TurnAction.SEARCH if typed_role == "user" else None,
        created_at_iso=f"2026-11-15T12:00:{idx % 60:02d}Z",
    )


def _make_google_ranked_offer() -> RankedOffer:
    offer = ProductOffer.model_validate(
        {
            "offer_id": "eg-google-1",
            "title": "Anker Soundcore Liberty 4 NC",
            "price": Decimal("3299.00"),
            "currency": CurrencyCode.EGP,
            "store": StoreId.AMAZON,
            "country": CountryCode.EG,
            "url": "https://www.google.com/shopping/product/99887766",
            "rating": 4.7,
            "review_count": 510,
        },
        context={"merchant_attribution": "Amazon.eg"},
    )
    return RankedOffer(
        rank=1,
        offer=offer,
        value_score=92.5,
        price_norm=0.9,
        bayesian_rating=4.67,
        match_reasons=("best_overall_value",),
    )


def _make_session_state(
    session_id: str,
    *,
    num_turns: int = 2,
    include_google_offer: bool = False,
) -> SessionState:
    ranked = [_make_google_ranked_offer()] if include_google_offer else []
    intent = SearchIntent(query="Anker earbuds", country=CountryCode.EG, language="en")
    turns = [_make_turn(i, role="user" if i % 2 == 0 else "assistant") for i in range(num_turns)]
    return SessionState(
        session_id=session_id,
        market=CountryCode.EG,
        last_intent=intent,
        last_ranked_offers=ranked,
        turns=turns,
        updated_at_epoch=1700000000.0,
    )


async def test_in_memory_session_store_lru_ttl_and_trimming() -> None:
    """T1.1 — InMemorySessionStore enforces bounded LRU, monotonic TTL, copies, and trimming."""
    clock = _FakeClock(100.0)
    store = InMemorySessionStore(clock=clock, max_sessions=2, max_turns=3)
    assert isinstance(store, SessionRepository)
    await store.initialize()

    s1 = _make_session_state("sess-1", num_turns=5, include_google_offer=True)
    await store.save_session(s1, ttl_seconds=60)
    # Mutating caller's SessionState after save must not affect stored state.
    s1.turns.append(_make_turn(99))
    s1.last_ranked_offers.clear()

    loaded_1 = await store.get_session("sess-1")
    assert loaded_1 is not None
    assert [t.content for t in loaded_1.turns] == ["turn-2", "turn-3", "turn-4"]
    assert len(loaded_1.last_ranked_offers) == 1
    # Mutating returned SessionState must not mutate store internals.
    loaded_1.turns.clear()
    loaded_1_again = await store.get_session("sess-1")
    assert loaded_1_again is not None
    assert len(loaded_1_again.turns) == 3

    await store.save_session(_make_session_state("sess-2", num_turns=2), ttl_seconds=60)
    # Touch sess-1 so sess-2 becomes the LRU key.
    assert await store.get_session("sess-1") is not None
    await store.save_session(_make_session_state("sess-3", num_turns=2), ttl_seconds=60)

    assert await store.get_session("sess-2") is None
    assert await store.get_session("sess-1") is not None
    assert await store.get_session("sess-3") is not None

    # Advance past TTL -> entries expire deterministically.
    clock.advance(60.0)
    assert await store.get_session("sess-1") is None
    assert await store.get_session("sess-3") is None

    await store.save_session(_make_session_state("sess-4", num_turns=2), ttl_seconds=30)
    await store.delete_session("sess-4")
    assert await store.get_session("sess-4") is None
    await store.close()


async def test_sqlalchemy_session_repository_crud_and_google_url_roundtrip(
    tmp_path: Path,
) -> None:
    """T1.2 — SQLAlchemySessionRepository auto-creates schema and round-trips Google URLs."""
    for db_url in (
        "sqlite+aiosqlite:///:memory:",
        f"sqlite+aiosqlite:///{(tmp_path / 'sessions.db').as_posix()}",
    ):
        repo = SQLAlchemySessionRepository(database_url=db_url, max_turns=3)
        assert isinstance(repo, SessionRepository)
        await repo.initialize()
        # Second initialize() must be idempotent.
        await repo.initialize()

        saved = _make_session_state("sess-sql-1", num_turns=5, include_google_offer=True)
        await repo.save_session(saved, ttl_seconds=120)

        loaded = await repo.get_session("sess-sql-1")
        assert loaded is not None
        assert loaded.session_id == "sess-sql-1"
        assert loaded.market == CountryCode.EG
        assert loaded.last_intent == saved.last_intent
        assert [t.content for t in loaded.turns] == ["turn-2", "turn-3", "turn-4"]
        assert len(loaded.last_ranked_offers) == 1
        assert (
            loaded.last_ranked_offers[0].offer.url
            == "https://www.google.com/shopping/product/99887766"
        )

        # Update existing row via merge/upsert.
        updated = loaded.model_copy(update={"market": CountryCode.SA})
        await repo.save_session(updated, ttl_seconds=120)
        reloaded = await repo.get_session("sess-sql-1")
        assert reloaded is not None
        assert reloaded.market == CountryCode.SA

        await repo.delete_session("sess-sql-1")
        assert await repo.get_session("sess-sql-1") is None
        await repo.delete_session("sess-sql-1")
        await repo.close()


def test_session_factory_resolves_sqlite_and_postgres_dialects(tmp_path: Path) -> None:
    """T1.3 — create_session_repository maps sqlite/postgresql dialects cleanly without DB I/O."""
    sqlite_settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'factory.db').as_posix()}",
    )
    sqlite_repo = create_session_repository(sqlite_settings)
    assert isinstance(sqlite_repo, ResilientSessionRepository)
    assert isinstance(sqlite_repo, SessionRepository)
    assert sqlite_repo.backend_name == "sqlite"
    assert sqlite_repo.is_degraded is False

    pg_settings = AppSettings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/commerce_ai",
    )
    pg_repo = create_session_repository(pg_settings)
    assert isinstance(pg_repo, ResilientSessionRepository)
    assert isinstance(pg_repo, SessionRepository)
    assert pg_repo.backend_name == "postgresql"
    assert pg_repo.is_degraded is False


async def test_in_memory_session_store_edge_cases() -> None:
    """T3.1 — InMemorySessionStore rejects invalid bounds, handles TTL<=0, and prunes expired."""
    with pytest.raises(ValueError, match="max_sessions"):
        InMemorySessionStore(max_sessions=0)
    with pytest.raises(ValueError, match="max_turns"):
        InMemorySessionStore(max_turns=1)

    clock = _FakeClock(50.0)
    store = InMemorySessionStore(clock=clock, max_sessions=2, max_turns=2)

    await store.delete_session("does-not-exist")
    await store.save_session(_make_session_state("zero-ttl"), ttl_seconds=0)
    assert await store.get_session("zero-ttl") is None

    # Save short-lived s1 and longer-lived s2.
    await store.save_session(_make_session_state("s1"), ttl_seconds=10)
    await store.save_session(_make_session_state("s2"), ttl_seconds=100)
    # Re-save s1 with non-positive ttl -> removes it cleanly.
    await store.save_session(_make_session_state("s1"), ttl_seconds=-5)
    assert await store.get_session("s1") is None

    # Fill capacity: short-lived s1 (10s) and long-lived s2 (100s), touch s1 so s2 is LRU.
    await store.save_session(_make_session_state("s1"), ttl_seconds=10)
    assert await store.get_session("s1") is not None
    clock.advance(15.0)  # s1 is expired, s2 is active even though s2 is older in LRU order!

    # Adding s3 must prune expired s1 first and retain active s2.
    await store.save_session(_make_session_state("s3"), ttl_seconds=100)
    assert await store.get_session("s1") is None
    assert await store.get_session("s2") is not None
    assert await store.get_session("s3") is not None


async def test_sqlalchemy_session_expiry_and_corrupt_payload(tmp_path: Path) -> None:
    """T3.2 — SQLAlchemySessionRepository cleans up expired rows and rejects corrupt JSON."""
    clock = _FakeClock(1000.0)
    db_path = tmp_path / "expiry.db"
    repo = SQLAlchemySessionRepository(
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        max_turns=4,
        wall_clock=clock,
    )
    await repo.initialize()

    await repo.save_session(_make_session_state("exp-1"), ttl_seconds=30)
    assert await repo.get_session("exp-1") is not None

    clock.advance(31.0)
    assert await repo.get_session("exp-1") is None

    # Verify the expired row was physically deleted from commerce_sessions.
    async with repo._engine.connect() as conn:
        row_count = (
            await conn.execute(
                text("SELECT COUNT(*) FROM commerce_sessions WHERE session_id = 'exp-1'")
            )
        ).scalar_one()
    assert row_count == 0

    # Inject corrupt JSON directly into commerce_sessions and confirm SessionStoreError.
    async with repo._engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO commerce_sessions "
                "(session_id, market, payload_json, expires_at_epoch, updated_at_epoch) "
                "VALUES ('bad-1', 'EG', '{corrupt-json', 9999999999.0, 1000.0)"
            )
        )
    with pytest.raises(SessionStoreError, match="Corrupt session payload"):
        await repo.get_session("bad-1")

    await repo.close()


async def test_sqlalchemy_error_redacts_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T3.3 (part 1) — SQLAlchemy errors scrub DB passwords across exceptions and logs."""
    secret_pw = "supersecretpw99"
    pg_url = f"postgresql+asyncpg://admin:{secret_pw}@127.0.0.1:5999/commerce_ai"

    with pytest.raises(SessionStoreError) as bad_driver_exc:
        SQLAlchemySessionRepository(database_url=f"mysql+aiomysql://admin:{secret_pw}@localhost/db")
    assert secret_pw not in str(bad_driver_exc.value)
    assert "***" in str(bad_driver_exc.value)

    def _fail_with_secret(*_args: object, **_kwargs: object) -> object:
        raise SQLAlchemyError(
            f"connection failed for {pg_url} (password={secret_pw}, token=tok123)"
        )

    repo = SQLAlchemySessionRepository(database_url=pg_url)
    try:
        # Simulate underlying driver failure containing raw URL + password.
        monkeypatch.setattr(AsyncEngine, "begin", _fail_with_secret)
        with pytest.raises(SessionStoreError) as init_exc:
            await repo.initialize()
        assert secret_pw not in str(init_exc.value)
        assert "tok123" not in str(init_exc.value)
        assert "***" in str(init_exc.value)

        caplog.set_level(logging.WARNING)
        settings = AppSettings(_env_file=None, database_url=pg_url)
        resilient = create_session_repository(settings)
        await resilient.initialize()

        assert resilient.is_degraded is True
        assert resilient.backend_name == "memory"
        assert secret_pw not in caplog.text
        assert "tok123" not in caplog.text
        await resilient.close()
    finally:
        await repo.close()


async def test_session_factory_fallback_on_init_and_runtime_errors(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T3.3 (part 2) — ResilientSessionRepository falls back on bad URL, init, or runtime I/O."""
    caplog.set_level(logging.WARNING)

    # 1. Defensively handle bypassed/mocked settings with empty or unsupported URL.
    empty_settings = SimpleNamespace(database_url="", session_max_turns=10)
    empty_repo = create_session_repository(empty_settings)  # type: ignore[arg-type]
    assert empty_repo.is_degraded is True
    assert empty_repo.backend_name == "memory"
    await empty_repo.initialize()
    await empty_repo.save_session(_make_session_state("mem-1"))
    loaded_mem = await empty_repo.get_session("mem-1")
    assert loaded_mem is not None and loaded_mem.session_id == "mem-1"
    await empty_repo.close()

    unsupported_settings = AppSettings(
        _env_file=None,
        database_url="mysql://admin:secretpw@127.0.0.1:3306/commerce_ai",
    )
    unsupported_repo = create_session_repository(unsupported_settings)
    assert unsupported_repo.is_degraded is True
    assert unsupported_repo.backend_name == "memory"
    assert "secretpw" not in caplog.text

    # 2. Unreachable PostgreSQL port degrades cleanly on initialize().
    unreachable_pg = AppSettings(
        _env_file=None,
        database_url="postgresql+asyncpg://admin:supersecretpw99@127.0.0.1:5999/commerce_ai",
    )
    pg_resilient = create_session_repository(unreachable_pg)
    assert pg_resilient.backend_name == "postgresql"
    assert pg_resilient.is_degraded is False
    await pg_resilient.initialize()
    assert pg_resilient.is_degraded is True
    assert pg_resilient.backend_name == "memory"
    assert "supersecretpw99" not in caplog.text
    await pg_resilient.save_session(_make_session_state("pg-fallback-1"))
    assert await pg_resilient.get_session("pg-fallback-1") is not None
    await pg_resilient.close()

    # 3. Runtime SQLite failure during save/get/delete fails over to InMemorySessionStore.
    sqlite_settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'runtime.db').as_posix()}",
    )
    runtime_repo = create_session_repository(sqlite_settings)
    await runtime_repo.initialize()
    assert runtime_repo.backend_name == "sqlite"
    assert runtime_repo.is_degraded is False

    assert runtime_repo._primary is not None

    async def _fail_save(*_args: object, **_kwargs: object) -> None:
        raise SessionStoreError("disk I/O failure")

    runtime_repo._primary.save_session = _fail_save  # type: ignore[method-assign]
    await runtime_repo.save_session(_make_session_state("rt-1"))
    assert runtime_repo.is_degraded is True
    assert runtime_repo.backend_name == "memory"
    rt_loaded = await runtime_repo.get_session("rt-1")
    assert rt_loaded is not None and rt_loaded.session_id == "rt-1"
    await runtime_repo.delete_session("rt-1")
    assert await runtime_repo.get_session("rt-1") is None
    await runtime_repo.close()


async def test_concurrent_same_session_upserts_and_ttl_cleanup(tmp_path: Path) -> None:
    """T4.2 — Dialect-native upsert handles concurrent writes, ttl<=0 delete, and 60s pruning."""
    clock = _FakeClock(initial=5000.0)
    db_urls = [
        f"sqlite+aiosqlite:///{(tmp_path / 'concurrent.db').as_posix()}",
        "sqlite+aiosqlite:///:memory:",
    ]
    for db_url in db_urls:
        repo = SQLAlchemySessionRepository(
            database_url=db_url,
            max_turns=10,
            wall_clock=clock,
            cleanup_interval_seconds=60.0,
        )
        await repo.initialize()

        # Concurrent first-turn writes on the same session_id succeed without UNIQUE conflicts.
        first_states = [_make_session_state("shared-s1", num_turns=1) for _ in range(8)]
        await asyncio.gather(*(repo.save_session(st, ttl_seconds=120) for st in first_states))
        loaded_first = await repo.get_session("shared-s1")
        assert loaded_first is not None
        assert loaded_first.session_id == "shared-s1"

        # Concurrent multi-turn updates overwrite cleanly.
        multi_states = [_make_session_state("shared-s1", num_turns=idx) for idx in range(2, 7)]
        await asyncio.gather(*(repo.save_session(st, ttl_seconds=120) for st in multi_states))
        assert await repo.get_session("shared-s1") is not None

        # ttl_seconds <= 0 deletes row instead of storing expired data.
        await repo.save_session(_make_session_state("shared-s1"), ttl_seconds=0)
        assert await repo.get_session("shared-s1") is None

        # Throttled expired-row cleanup prunes at most once per cleanup_interval_seconds.
        await repo.save_session(_make_session_state("exp-1"), ttl_seconds=10)
        await repo.save_session(_make_session_state("exp-2"), ttl_seconds=10)
        clock.advance(20.0)  # both expired, still < 60s since last cleanup
        await repo.save_session(_make_session_state("live-1"), ttl_seconds=300)
        async with repo._session_factory() as db_sess:
            mid_count = (
                await db_sess.execute(text("SELECT COUNT(*) FROM commerce_sessions"))
            ).scalar_one()
        assert mid_count == 3

        clock.advance(45.0)  # >= 60s elapsed -> next save triggers DELETE cleanup
        await repo.save_session(_make_session_state("live-2"), ttl_seconds=300)
        async with repo._session_factory() as db_sess:
            after_count = (
                await db_sess.execute(text("SELECT COUNT(*) FROM commerce_sessions"))
            ).scalar_one()
        assert after_count == 2
        await repo.close()

    # InMemorySessionStore handles concurrent same-session upserts cleanly too.
    mem_store = InMemorySessionStore(clock=clock, max_turns=10)
    await asyncio.gather(
        *(mem_store.save_session(_make_session_state("mem-same", num_turns=i)) for i in range(1, 6))
    )
    mem_loaded = await mem_store.get_session("mem-same")
    assert mem_loaded is not None and mem_loaded.session_id == "mem-same"


async def test_resilient_session_cooldown_recovery_and_data_error_isolation(
    tmp_path: Path,
) -> None:
    """T4.3 — Startup close, 30s cooldown recovery probe, and SessionDataError non-degradation."""
    # 1. Startup initialize() failure calls primary.close() and nulls _primary.
    close_calls = 0
    broken_primary = SQLAlchemySessionRepository(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'startup_close.db').as_posix()}",
    )

    async def _fail_init() -> None:
        raise SessionStoreError("startup connection failed")

    orig_close = broken_primary.close

    async def _counting_close() -> None:
        nonlocal close_calls
        close_calls += 1
        await orig_close()

    broken_primary.initialize = _fail_init  # type: ignore[method-assign]
    broken_primary.close = _counting_close  # type: ignore[method-assign]
    startup_repo = ResilientSessionRepository(
        primary=broken_primary,
        fallback=InMemorySessionStore(),
        primary_backend="sqlite",
    )
    await startup_repo.initialize()
    assert close_calls == 1
    assert startup_repo._primary is None
    assert startup_repo.is_degraded is True
    await startup_repo.close()

    # 2. Runtime degradation stays in memory during 30s cooldown, then recovers automatically.
    clock = _FakeClock(initial=2000.0)
    primary = SQLAlchemySessionRepository(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'cooldown.db').as_posix()}",
    )
    fallback = InMemorySessionStore()
    repo = ResilientSessionRepository(
        primary=primary,
        fallback=fallback,
        primary_backend="sqlite",
        recovery_cooldown_seconds=30.0,
        clock=clock,
    )
    await repo.initialize()

    orig_get = primary.get_session
    orig_save = primary.save_session
    fail_mode = True
    primary_attempts = 0

    async def _flaky_save(state: SessionState, ttl_seconds: int = 86400) -> None:
        nonlocal primary_attempts
        primary_attempts += 1
        if fail_mode:
            raise SessionStoreError("transient lock")
        await orig_save(state, ttl_seconds=ttl_seconds)

    async def _flaky_get(session_id: str) -> SessionState | None:
        nonlocal primary_attempts
        primary_attempts += 1
        if fail_mode:
            raise SessionStoreError("transient lock")
        return await orig_get(session_id)

    primary.save_session = _flaky_save  # type: ignore[method-assign]
    primary.get_session = _flaky_get  # type: ignore[method-assign]

    await repo.save_session(_make_session_state("rec-1"))
    assert repo.is_degraded is True
    assert repo.backend_name == "memory"
    assert primary_attempts == 1

    # Within cooldown (< 30s), primary is NOT called at all.
    clock.advance(10.0)
    assert await repo.get_session("rec-1") is not None
    assert primary_attempts == 1

    # After cooldown (>= 30s) and primary recovery, probe clears degradation.
    fail_mode = False
    clock.advance(25.0)
    recovered_state = await repo.get_session("rec-1")
    assert recovered_state is not None
    assert primary_attempts == 2
    assert repo.is_degraded is False
    assert repo.backend_name == "sqlite"

    # 3. Per-row SessionDataError does NOT mark backend degraded.
    async def _corrupt_get(session_id: str) -> SessionState | None:
        raise SessionDataError("corrupt single row payload")

    primary.get_session = _corrupt_get  # type: ignore[method-assign]
    corrupt_fallback = await repo.get_session("rec-1")
    assert corrupt_fallback is not None
    assert repo.is_degraded is False
    assert repo.backend_name == "sqlite"

    await repo.close()
