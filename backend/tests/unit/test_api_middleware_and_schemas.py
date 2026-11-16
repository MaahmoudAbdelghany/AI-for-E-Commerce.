"""Offline unit tests for Feature 2.3 schemas, dependencies, middleware, and error handlers."""

from __future__ import annotations

import ast
import logging
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport
from pydantic import SecretStr, ValidationError

from commerce_ai.adapters.catalog.seed_provider import SeedCatalogProvider
from commerce_ai.adapters.llm.fake import FakeLLMClient
from commerce_ai.adapters.session.factory import ResilientSessionRepository
from commerce_ai.adapters.session.memory import InMemorySessionStore
from commerce_ai.agent.graph import ShoppingAssistantWorkflow
from commerce_ai.api.dependencies import (
    get_catalog_provider,
    get_request_id,
    get_settings,
    get_workflow,
)
from commerce_ai.api.errors import register_exception_handlers
from commerce_ai.api.middleware import (
    RequestIDMiddleware,
    SlidingWindowRateLimiter,
    configure_middleware,
    extract_client_ip,
)
from commerce_ai.api.schemas import (
    ChatRequest,
    ErrorResponse,
    HealthResponse,
    MarketInfoSchema,
    MarketsResponse,
    MarketStoreSchema,
    SearchRequest,
)
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.errors import (
    CatalogProviderError,
    DomainError,
    LLMProviderError,
    OfferValidationError,
)
from commerce_ai.domain.models import CountryCode, CurrencyCode, StoreId
from commerce_ai.main import create_app


class _FakeClock:
    def __init__(self, initial: float = 100.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, delta: float) -> None:
        self.now += delta


def _make_settings(**overrides: Any) -> AppSettings:
    defaults: dict[str, Any] = {
        "_env_file": None,
        "catalog_mode": "seed",
        "llm_mode": "fake",
        "cors_allowed_origins": ["http://localhost:3000"],
        "rate_limit_rpm": 60,
    }
    defaults.update(overrides)
    return AppSettings(**defaults)


def _build_middleware_probe_app(
    settings: AppSettings,
    *,
    clock: _FakeClock | None = None,
) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    register_exception_handlers(app)
    configure_middleware(app, settings, clock=clock)

    @app.get("/health")
    async def _health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/markets")
    async def _markets() -> dict[str, str]:
        return {"markets": "ok"}

    @app.post("/api/v1/search")
    async def _search(request: Request) -> dict[str, str]:
        return {"request_id": get_request_id(request)}

    @app.post("/api/v1/chat")
    async def _chat(request: Request) -> dict[str, str]:
        return {"request_id": get_request_id(request)}

    @app.post("/validate")
    async def _validate(payload: SearchRequest) -> dict[str, str]:
        return {"query": payload.query}

    @app.get("/err/catalog")
    async def _err_catalog() -> dict[str, str]:
        raise CatalogProviderError(
            provider="serper",
            retriable=True,
            reason=(
                "upstream timeout https://google.serper.dev/shopping?token=secret123 "
                "Bearer bearersecret999"
            ),
        )

    @app.get("/err/offer")
    async def _err_offer() -> dict[str, str]:
        raise OfferValidationError("invalid regional offer url")

    @app.get("/err/domain")
    async def _err_domain() -> dict[str, str]:
        raise DomainError("invalid domain constraint")

    @app.get("/err/llm")
    async def _err_llm() -> dict[str, str]:
        raise LLMProviderError(
            provider="gemini",
            retriable=False,
            reason="quota failed AIzaFakeSecretKey987654321",
        )

    @app.get("/err/boom")
    async def _err_boom() -> dict[str, str]:
        raise RuntimeError(
            "postgresql://user:supersecret@db/app Bearer boomtoken888\n"
            'Traceback (most recent call last):\n  File "app.py", line 1, in <module>'
        )

    return app


async def test_request_id_middleware_propagates_and_sanitizes() -> None:
    """T1.1: Valid X-Request-ID is preserved; missing, unsafe, or oversized IDs become UUID4."""
    settings = _make_settings(rate_limit_rpm=0)
    app = _build_middleware_probe_app(settings)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        valid_res = await client.post(
            "/api/v1/search",
            headers={"X-Request-ID": "req-phase2-abc_123"},
        )
        assert valid_res.status_code == 200
        assert valid_res.headers["X-Request-ID"] == "req-phase2-abc_123"
        assert valid_res.json()["request_id"] == "req-phase2-abc_123"

        missing_res = await client.post("/api/v1/search")
        assert missing_res.status_code == 200
        generated_id = missing_res.headers["X-Request-ID"]
        assert uuid.UUID(generated_id).version == 4
        assert missing_res.json()["request_id"] == generated_id

        for bad_header in ("", "has spaces", "bad$id!", "a" * 200):
            unsafe_res = await client.post(
                "/api/v1/search",
                headers={"X-Request-ID": bad_header},
            )
            assert unsafe_res.status_code == 200
            replacement_id = unsafe_res.headers["X-Request-ID"]
            assert replacement_id != bad_header
            assert uuid.UUID(replacement_id).version == 4

    # Verify raw ASGI CRLF header injection is also sanitized directly at the middleware boundary.
    captured_headers: list[tuple[bytes, bytes]] = []
    captured_state_id: str | None = None

    async def _inner_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        nonlocal captured_state_id
        captured_state_id = scope["state"]["request_id"]
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    async def _receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def _send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            captured_headers.extend(message["headers"])

    middleware = RequestIDMiddleware(_inner_app)  # type: ignore[arg-type]
    await middleware(
        {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [(b"x-request-id", b"bad\r\nid")],
        },
        _receive,
        _send,
    )
    assert captured_state_id is not None
    assert "\r" not in captured_state_id
    assert "\n" not in captured_state_id
    assert uuid.UUID(captured_state_id).version == 4
    header_map = {k.lower(): v.decode("latin1") for k, v in captured_headers}
    assert header_map[b"x-request-id"] == captured_state_id


async def test_cors_middleware_origins_and_exposed_headers() -> None:
    """T1.2: Allowed origin receives CORS headers + exposed headers; disallowed gets none."""
    settings = _make_settings(
        cors_allowed_origins=["http://localhost:3000"],
        rate_limit_rpm=0,
    )
    app = _build_middleware_probe_app(settings)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        preflight_ok = await client.options(
            "/api/v1/chat",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-request-id",
            },
        )
        assert preflight_ok.status_code == 200
        assert preflight_ok.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "POST" in preflight_ok.headers["access-control-allow-methods"]
        assert "access-control-allow-credentials" not in preflight_ok.headers
        assert "x-request-id" in preflight_ok.headers

        normal_ok = await client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert normal_ok.status_code == 200
        assert normal_ok.headers["access-control-allow-origin"] == "http://localhost:3000"
        exposed = normal_ok.headers["access-control-expose-headers"]
        assert "X-Request-ID" in exposed
        assert "Retry-After" in exposed
        assert "access-control-allow-credentials" not in normal_ok.headers

        preflight_bad = await client.options(
            "/api/v1/chat",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-origin" not in preflight_bad.headers

        normal_bad = await client.get(
            "/health",
            headers={"Origin": "https://evil.example"},
        )
        assert normal_bad.status_code == 200
        assert "access-control-allow-origin" not in normal_bad.headers


async def test_sliding_window_rate_limiter_and_exemptions() -> None:
    """T1.3: Sliding-window 429 enforcement, Retry-After, clock reset, disable, and exemptions."""
    clock = _FakeClock(initial=1000.0)
    settings = _make_settings(
        rate_limit_rpm=3,
        cors_allowed_origins=["http://localhost:3000"],
    )
    app = _build_middleware_probe_app(settings, clock=clock)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app, client=("198.51.100.5", 4321)),
        base_url="http://test",
    ) as client:
        assert (await client.post("/api/v1/search")).status_code == 200
        clock.advance(1.0)
        assert (await client.post("/api/v1/chat")).status_code == 200
        clock.advance(1.0)
        assert (await client.post("/api/v1/search")).status_code == 200

        blocked = await client.post(
            "/api/v1/chat",
            headers={"Origin": "http://localhost:3000"},
        )
        assert blocked.status_code == 429
        retry_after = int(blocked.headers["Retry-After"])
        assert 1 <= retry_after <= 60
        assert blocked.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "Retry-After" in blocked.headers["access-control-expose-headers"]

        err_body = ErrorResponse.model_validate(blocked.json())
        assert err_body.error_code == "rate_limit_exceeded"
        assert err_body.retriable is True
        assert err_body.request_id == blocked.headers["X-Request-ID"]

        # Exempt paths stay 200 even while the client is rate-limited.
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/api/v1/markets")).status_code == 200

        # Advancing clock past the 60s window clears expired timestamps.
        clock.advance(60.0)
        after_window = await client.post("/api/v1/search")
        assert after_window.status_code == 200

    # rate_limit_rpm=0 disables limiting completely.
    disabled_app = _build_middleware_probe_app(_make_settings(rate_limit_rpm=0), clock=clock)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=disabled_app),
        base_url="http://test",
    ) as client:
        for _ in range(10):
            assert (await client.post("/api/v1/search")).status_code == 200

    # Unit checks for bounded LRU eviction and extract_client_ip validation.
    limiter = SlidingWindowRateLimiter(limit_rpm=1, max_clients=2, clock=clock)
    assert (await limiter.check("10.0.0.1"))[0] is True
    assert (await limiter.check("10.0.0.2"))[0] is True
    assert (await limiter.check("10.0.0.3"))[0] is True
    assert (await limiter.check("10.0.0.1"))[0] is True  # evicted oldest client bucket

    # Untrusted peer (or no trusted proxies) ignores X-Forwarded-For completely.
    assert (
        extract_client_ip(
            {
                "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")],
                "client": ("127.0.0.1", 1),
            }
        )
        == "127.0.0.1"
    )
    assert (
        extract_client_ip(
            {
                "headers": [(b"x-forwarded-for", b"198.51.100.99")],
                "client": ("198.51.100.5", 1),
            },
            trusted_proxies=("127.0.0.1/32",),
        )
        == "198.51.100.5"
    )
    # Trusted proxy walks right-to-left and picks the rightmost untrusted hop.
    assert (
        extract_client_ip(
            {
                "headers": [(b"x-forwarded-for", b"1.1.1.1, 203.0.113.9, 10.0.0.2")],
                "client": ("127.0.0.1", 1),
            },
            trusted_proxies=("127.0.0.1/32", "10.0.0.0/8"),
        )
        == "203.0.113.9"
    )
    assert (
        extract_client_ip(
            {"headers": [(b"x-forwarded-for", b"spoofed;evil")], "client": ("127.0.0.1", 1)},
            trusted_proxies=("127.0.0.1/32",),
        )
        == "127.0.0.1"
    )
    assert (
        extract_client_ip(
            {"headers": [(b"x-forwarded-for", b"10.0.0.2")], "client": ("127.0.0.1", 1)},
            trusted_proxies=("127.0.0.1/32", "10.0.0.0/8"),
        )
        == "127.0.0.1"
    )

    # Integration through middleware: untrusted peer rotating XFF cannot evade rate limit.
    spoof_app = _build_middleware_probe_app(
        _make_settings(rate_limit_rpm=2, trusted_proxy_cidrs=["127.0.0.1/32"]),
        clock=clock,
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=spoof_app, client=("198.51.100.42", 4321)),
        base_url="http://test",
    ) as client:
        assert (
            await client.post("/api/v1/search", headers={"X-Forwarded-For": "1.2.3.4"})
        ).status_code == 200
        assert (
            await client.post("/api/v1/search", headers={"X-Forwarded-For": "5.6.7.8"})
        ).status_code == 200
        spoof_blocked = await client.post(
            "/api/v1/search",
            headers={"X-Forwarded-For": "9.10.11.12"},
        )
        assert spoof_blocked.status_code == 429

    # Trusted proxy separates distinct real client IPs from rightmost untrusted hop.
    proxy_app = _build_middleware_probe_app(
        _make_settings(rate_limit_rpm=1, trusted_proxy_cidrs=["127.0.0.1/32", "10.0.0.0/8"]),
        clock=clock,
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=proxy_app, client=("127.0.0.1", 4321)),
        base_url="http://test",
    ) as client:
        assert (
            await client.post(
                "/api/v1/search",
                headers={"X-Forwarded-For": "203.0.113.10, 10.0.0.5"},
            )
        ).status_code == 200
        assert (
            await client.post(
                "/api/v1/search",
                headers={"X-Forwarded-For": "203.0.113.11, 10.0.0.5"},
            )
        ).status_code == 200
        assert (
            await client.post(
                "/api/v1/search",
                headers={"X-Forwarded-For": "203.0.113.10, 10.0.0.5"},
            )
        ).status_code == 429


async def test_error_handlers_emit_sanitized_error_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T1.4: Unified ErrorResponse handlers mask secrets and preserve X-Request-ID + CORS."""
    settings = _make_settings(
        rate_limit_rpm=0,
        cors_allowed_origins=["http://localhost:3000"],
        serper_api_key=SecretStr("serper-secret-token"),
        gemini_api_key=SecretStr("AIzaFakeSecretKey987654321"),
        database_url="postgresql+asyncpg://user:supersecret@db/app",
    )
    app = _build_middleware_probe_app(settings)
    caplog.set_level(logging.ERROR)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        headers = {"Origin": "http://localhost:3000", "X-Request-ID": "req-err-01"}

        val_res = await client.post("/validate", json={"query": "   "}, headers=headers)
        assert val_res.status_code == 422
        val_err = ErrorResponse.model_validate(val_res.json())
        assert val_err.error_code == "validation_error"
        assert val_err.retriable is False
        assert val_err.request_id == val_res.headers["X-Request-ID"] == "req-err-01"
        assert val_res.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert val_err.details is not None and len(val_err.details) >= 1
        assert all("input" not in detail for detail in val_err.details)

        bad_input_res = await client.post(
            "/validate",
            json={"query": "earbuds", "max_budget": "secret_user_input_12345"},
            headers=headers,
        )
        assert bad_input_res.status_code == 422
        assert "secret_user_input_12345" not in bad_input_res.text

        bad_json_res = await client.post(
            "/validate",
            content=b"{not-valid-json",
            headers={**headers, "Content-Type": "application/json"},
        )
        assert bad_json_res.status_code == 422
        bad_json_err = ErrorResponse.model_validate(bad_json_res.json())
        assert bad_json_err.error_code == "validation_error"
        assert bad_json_err.request_id == bad_json_res.headers["X-Request-ID"] == "req-err-01"

        cat_res = await client.get("/err/catalog", headers=headers)
        assert cat_res.status_code == 503
        cat_err = ErrorResponse.model_validate(cat_res.json())
        assert cat_err.error_code == "catalog_unavailable"
        assert cat_err.retriable is True
        assert cat_err.request_id == cat_res.headers["X-Request-ID"]
        assert "secret123" not in cat_res.text
        assert "bearersecret999" not in cat_res.text
        assert "Bearer ***" in cat_err.message

        offer_res = await client.get("/err/offer", headers=headers)
        assert offer_res.status_code == 422
        offer_err = ErrorResponse.model_validate(offer_res.json())
        assert offer_err.error_code == "offer_validation_error"
        assert offer_err.retriable is False

        dom_res = await client.get("/err/domain", headers=headers)
        assert dom_res.status_code == 400
        dom_err = ErrorResponse.model_validate(dom_res.json())
        assert dom_err.error_code == "domain_error"
        assert dom_err.retriable is False

        llm_res = await client.get("/err/llm", headers=headers)
        assert llm_res.status_code == 503
        llm_err = ErrorResponse.model_validate(llm_res.json())
        assert llm_err.error_code == "llm_unavailable"
        assert llm_err.retriable is False
        assert "AIzaFakeSecretKey987654321" not in llm_res.text

        boom_res = await client.get("/err/boom", headers=headers)
        assert boom_res.status_code == 500
        boom_err = ErrorResponse.model_validate(boom_res.json())
        assert boom_err.error_code == "internal_error"
        assert boom_err.retriable is False
        assert boom_err.message == "An unexpected internal error occurred."
        assert boom_err.request_id == boom_res.headers["X-Request-ID"] == "req-err-01"
        assert boom_res.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "supersecret" not in boom_res.text
        assert "boomtoken888" not in boom_res.text
        assert "postgresql://" not in boom_res.text
        assert "Traceback" not in boom_res.text
        assert 'File "app.py"' not in boom_res.text

    assert "supersecret" not in caplog.text
    assert "boomtoken888" not in caplog.text
    assert "Traceback (most recent call last):" not in caplog.text


async def test_health_response_has_zero_secrets_and_degraded_flag() -> None:
    """T1.5: /health emits ok vs degraded flags with zero API keys, DB passwords, or raw URLs."""
    secret_settings = AppSettings(
        _env_file=None,
        serper_api_key=SecretStr("serper-secret-xyz"),
        gemini_api_key=SecretStr("AIzaDummyGeminiSecret999"),
        groq_api_key=SecretStr("gsk_DummyGroqSecret888"),
        openai_api_key=SecretStr("sk-DummyOpenAISecret777"),
        redis_url="redis://:redispass@redis:6379/0",
        database_url="postgresql+asyncpg://dbuser:dbpass@pg:5432/db",
    )
    app = create_app(secret_settings)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        healthy_res = await client.get("/health")
        assert healthy_res.status_code == 200
        healthy_payload = HealthResponse.model_validate(healthy_res.json())
        assert healthy_payload.status == "ok"
        assert healthy_payload.cache_backend == "memory"
        assert healthy_payload.session_backend == "postgresql"
        assert healthy_payload.version == "0.1.0"

        # Simulate degraded cache & session fallback without mutating secrets.
        app.state.cache_degraded = True
        app.state.session_repository = ResilientSessionRepository(
            primary=None,
            fallback=InMemorySessionStore(),
            primary_backend="memory",
        )
        degraded_res = await client.get("/health")
        assert degraded_res.status_code == 200
        degraded_payload = HealthResponse.model_validate(degraded_res.json())
        assert degraded_payload.status == "degraded"
        assert degraded_payload.session_backend == "memory"

    forbidden_substrings = (
        "redispass",
        "dbpass",
        "serper-secret-xyz",
        "AIzaDummyGeminiSecret999",
        "gsk_DummyGroqSecret888",
        "sk-DummyOpenAISecret777",
        "redis://",
        "postgresql+asyncpg://",
        "pg:5432",
    )
    for raw_text in (healthy_res.text, degraded_res.text):
        for secret in forbidden_substrings:
            assert secret not in raw_text


def test_api_schema_validation_boundaries() -> None:
    """T1.6: DTO bounds for ChatRequest, SearchRequest, and MarketsResponse."""
    # ChatRequest lets raw message strings pass to workflow guardrails while validating filters.
    raw_empty = ChatRequest(message="")
    assert raw_empty.message == ""
    raw_long = ChatRequest(message="x" * 2500, session_id="  sess-123  ")
    assert len(raw_long.message) == 2500
    assert raw_long.session_id == "sess-123"
    assert raw_long.country == CountryCode.EG

    assert ChatRequest(message="hi", max_budget=Decimal("10000000.00")).max_budget == Decimal(
        "10000000.00"
    )
    for bad_chat in (
        {"message": "hi", "extra": 1},
        {"message": "hi", "country": "US"},
        {"message": "hi", "max_budget": 0},
        {"message": "hi", "max_budget": -5},
        {"message": "hi", "max_budget": "10000000.01"},
        {"message": "hi", "max_budget": "1e50"},
        {"message": "hi", "language": "fr"},
        {"message": "hi", "session_id": ""},
        {"message": "hi", "session_id": "   "},
        {"message": "hi", "session_id": "a" * 129},
        {"message": "hi", "session_id": "bad\nid"},
        {"message": "hi", "session_id": "bad\u202eid"},
        {"message": "hi", "session_id": "bad\U000e0069id"},
    ):
        with pytest.raises(ValidationError):
            ChatRequest.model_validate(bad_chat)

    # SearchRequest strictly validates query, bounds, and extra fields.
    valid_search = SearchRequest(
        query="  Anker earbuds  ", min_rating=4.5, max_budget=Decimal("10000000.00")
    )
    assert valid_search.query == "Anker earbuds"
    for bad_search in (
        {"query": ""},
        {"query": "   "},
        {"query": "a" * 501},
        {"query": "earbuds\x00"},
        {"query": "earbuds\x1b[31m"},
        {"query": "earbuds\u202efake"},
        {"query": "earbuds\u2066hidden"},
        {"query": "earbuds\U000e0069tag"},
        {"query": "earbuds", "max_budget": 0},
        {"query": "earbuds", "max_budget": "10000000.01"},
        {"query": "earbuds", "max_budget": "1e50"},
        {"query": "earbuds", "min_rating": -0.1},
        {"query": "earbuds", "min_rating": 5.1},
        {"query": "earbuds", "country": "US"},
        {"query": "earbuds", "unknown": True},
    ):
        with pytest.raises(ValidationError):
            SearchRequest.model_validate(bad_search)

    markets = MarketsResponse(
        markets=[
            MarketInfoSchema(
                country=CountryCode.EG,
                currency=CurrencyCode.EGP,
                name_en="Egypt",
                name_ar="مصر",
                currency_label_en="EGP",
                currency_label_ar="جنيه مصري",
                serper_gl="eg",
                stores=[
                    MarketStoreSchema(
                        store_id=StoreId.NOON,
                        label_en="Noon",
                        label_ar="نون",
                        primary_domain="noon.com",
                    ),
                    MarketStoreSchema(
                        store_id=StoreId.AMAZON,
                        label_en="Amazon",
                        label_ar="أمازون",
                        primary_domain="amazon.eg",
                    ),
                ],
            )
        ],
        request_id="req-1",
    )
    assert markets.markets[0].currency == CurrencyCode.EGP


async def test_dependencies_and_api_hexagonal_boundary() -> None:
    """T1.7: Typed Depends resolve from app.state/request.state and api/ obeys INV-02."""
    settings = _make_settings()
    catalog = SeedCatalogProvider()
    workflow = ShoppingAssistantWorkflow(
        settings=settings,
        catalog_provider=catalog,
        session_repository=InMemorySessionStore(),
        llm_client=FakeLLMClient(),
    )

    probe = FastAPI()
    probe.state.settings = settings
    probe.state.catalog_provider = catalog
    probe.state.workflow = workflow

    @probe.get("/deps")
    async def _deps_route(
        request: Request,
        dep_settings: AppSettings = Depends(get_settings),  # noqa: B008
        dep_workflow: ShoppingAssistantWorkflow = Depends(get_workflow),  # noqa: B008
        dep_catalog: SeedCatalogProvider = Depends(get_catalog_provider),  # type: ignore[assignment]  # noqa: B008
        dep_req_id: str = Depends(get_request_id),  # noqa: B008
    ) -> dict[str, Any]:
        assert dep_settings is settings
        assert dep_workflow is workflow
        assert dep_catalog is catalog
        return {"request_id": dep_req_id, "state_id": request.state.request_id}

    async with httpx.AsyncClient(
        transport=ASGITransport(app=probe),
        base_url="http://test",
    ) as client:
        res = await client.get("/deps")
        assert res.status_code == 200
        body = res.json()
        assert uuid.UUID(body["request_id"]).version == 4
        assert body["request_id"] == body["state_id"]

    # Missing state raises explicit RuntimeError rather than returning None.
    empty_app = FastAPI()
    empty_req = Request({"type": "http", "app": empty_app, "headers": []})
    with pytest.raises(RuntimeError):
        get_settings(empty_req)
    with pytest.raises(RuntimeError):
        get_workflow(empty_req)
    with pytest.raises(RuntimeError):
        get_catalog_provider(empty_req)

    # AST hexagonal boundary check across every file under commerce_ai/api/.
    forbidden_prefixes = (
        "httpx",
        "redis",
        "sqlalchemy",
        "asyncpg",
        "aiosqlite",
        "openai",
        "groq",
        "google",
        "litellm",
        "serper",
        "commerce_ai.adapters",
    )
    api_dir = Path(__file__).resolve().parents[2] / "src" / "commerce_ai" / "api"
    py_files = sorted(api_dir.glob("*.py"))
    assert len(py_files) >= 6
    for file_path in py_files:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append(node.module)
        for mod in imported:
            for forbidden in forbidden_prefixes:
                assert not (mod == forbidden or mod.startswith(f"{forbidden}.")), (
                    f"Forbidden import {mod!r} found in {file_path.name}"
                )
