# Validation Criteria: Feature 2.3 — Versioned FastAPI Service, Middleware & API Contracts

## 1. Success Definition

Feature 2.3 is complete when `commerce_ai.main:create_app` and module-level `app` wire all Phase 1–2 ports/factories cleanly with resilient async `lifespan` initialization and resource cleanup, `api/schemas.py`, `api/dependencies.py`, `api/middleware.py`, `api/errors.py`, and `api/routes.py` expose `/api/v1/chat`, `/api/v1/search`, `/api/v1/markets`, `/health`, and `/openapi.json` (`3.1`, `version="0.1.0"`) with zero secret or stack-trace leakage (`INV-01`, `INV-09`), all unit and `ASGITransport` integration checks in `backend/tests/unit/test_api_middleware_and_schemas.py` and `backend/tests/integration/test_fastapi_endpoints.py` pass 100% offline (`< 30 s`, repeat search `< 300 ms`, `INV-07`), and `pytest -v`, `ruff check .`, `ruff format --check .`, `mypy src`, `uv lock --check`, and Tier 7 ASGI verification all pass with zero errors (only upstream third-party `LangChainPendingDeprecationWarning` from `langgraph` if emitted).

---

## 2. Requirement Traceability

| Requirement | Checks |
| :--- | :--- |
| R1 | T2.1, T2.4, T3.5, T7.1 |
| R2 | T1.7, T2.1, T2.2, T2.3 |
| R3 | T1.5, T1.6, T3.1, T3.3 |
| R4 | T2.3, T3.1, T3.2, T7.1 |
| R5 | T2.2, T3.2, T3.3, T7.1 |
| R6 | T1.6, T2.1, T7.1 |
| R7 | T1.5, T2.1, T3.5, T7.1 |
| R8 | T1.1, T1.2, T2.1, T3.4 |
| R9 | T1.3, T3.4 |
| R10 | T1.4, T3.2, T3.3, T3.5 |
| NFR1 | T2.2 |
| NFR2 | T1.4, T1.5, T3.1, T3.4, T3.5 |
| NFR3 | T1.7, T2.2, T2.3, T4.1 |
| NFR4 | T2.4, T5.1, T5.2, T5.3, T5.4 |

---

## 3. Verification Tiers

### Tier 1: Unit Verification

- [x] **T1.1 — `X-Request-ID` Propagation & Generation**: Send requests with a valid `X-Request-ID` (`"req-phase2-abc_123"`), without `X-Request-ID`, and with an unsafe/oversized header (`"bad\r\nid"` / `200`-char string) → valid ID is preserved in `request.state.request_id` and returned on response `X-Request-ID`; missing or unsafe IDs are replaced with a valid UUID4 (`backend/tests/unit/test_api_middleware_and_schemas.py::test_request_id_middleware_propagates_and_sanitizes`).
- [x] **T1.2 — `CORSMiddleware` Configuration & Exposed Headers**: Issue `OPTIONS` preflight and normal requests from an allowed origin (`http://localhost:3000`) and a disallowed origin (`https://evil.example`) → allowed origin receives `Access-Control-Allow-Origin: http://localhost:3000` and exposes `X-Request-ID` and `Retry-After` (`allow_credentials` absent/false); disallowed origin does not receive allow headers (`backend/tests/unit/test_api_middleware_and_schemas.py::test_cors_middleware_origins_and_exposed_headers`).
- [x] **T1.3 — Sliding-Window Rate Limiter Core Mechanics**: Configure `rate_limit_rpm=3` with an injectable monotonic `clock` → first 3 requests to `/api/v1/search` and `/api/v1/chat` succeed; 4th request returns HTTP `429` with `Retry-After` (`1..60`), `X-Request-ID`, CORS headers, and `ErrorResponse(error_code="rate_limit_exceeded", retriable=True)`; advancing the clock by `60.0s` allows requests again; `rate_limit_rpm=0` disables limiting; `/health` and `/api/v1/markets` remain exempt (`backend/tests/unit/test_api_middleware_and_schemas.py::test_sliding_window_rate_limiter_and_exemptions`).
- [x] **T1.4 — Unified `ErrorResponse` Exception Handlers & Secret Scrubbing (`INV-01`)**: Trigger `RequestValidationError` (`422`), `CatalogProviderError(provider="serper", retriable=True, reason=...)` (`503`), `OfferValidationError` (`422`), `DomainError` (`400`), `LLMProviderError` (`503`), and an unhandled `RuntimeError("postgresql://user:supersecret@db/app")` (`500`) → each returns JSON matching `ErrorResponse` (`error_code`, `retriable`, `request_id`), `500` emits a generic safe message without `"supersecret"` or Python stack traces, and `X-Request-ID` matches `body["request_id"]` (`backend/tests/unit/test_api_middleware_and_schemas.py::test_error_handlers_emit_sanitized_error_response`).
- [x] **T1.5 — `HealthResponse` Schema & Zero-Secret Enforcement (`INV-01`)**: Build apps with populated secret settings (`serper_api_key`, `gemini_api_key`, `groq_api_key`, `openai_api_key`, `redis_url="redis://:redispass@redis:6379/0"`, `database_url="postgresql+asyncpg://dbuser:dbpass@pg:5432/db"`) in healthy and degraded fallback states → serialized `HealthResponse` reports valid `status` (`"ok"` vs `"degraded"`), `cache_backend`, `session_backend`, and `version="0.1.0"`, and contains zero secret substrings (`redispass`, `dbpass`, API keys, or raw URLs) (`backend/tests/unit/test_api_middleware_and_schemas.py::test_health_response_has_zero_secrets_and_degraded_flag`).
- [x] **T1.6 — Request/Response DTO Contracts (`ChatRequest`, `SearchRequest`, `MarketsResponse`)**: Verify `ChatRequest` rejects unknown extra keys, invalid `country`, `max_budget <= 0`, and blank/control-char `session_id` while allowing raw `message: str` (including empty/long strings for downstream guardrail refusal); verify `SearchRequest` enforces `query` `1..500` non-blank chars, `max_budget > 0`, `min_rating` in `0.0..5.0`, and `extra="forbid"`; verify `MarketsResponse` enumerates `EG`/`EGP`, `SA`/`SAR`, `AE`/`AED` and stores `noon`/`amazon` (`backend/tests/unit/test_api_middleware_and_schemas.py::test_api_schema_validation_boundaries`).
- [x] **T1.7 — Typed `Depends` Accessors & Hexagonal Import Boundary (`INV-02`)**: Verify `get_settings`, `get_workflow`, `get_catalog_provider`, and `get_request_id` resolve from `request.app.state` / `request.state`, and run an AST import check confirming `commerce_ai/api/` contains zero direct imports from `httpx`, `redis`, `sqlalchemy`, or LLM/Serper adapter clients (`backend/tests/unit/test_api_middleware_and_schemas.py::test_dependencies_and_api_hexagonal_boundary`).

### Tier 2: Integration Verification

- [x] **T2.1 — `GET /health` & `GET /api/v1/markets` via `ASGITransport` + Lifespan**: Boot `create_app(...)` with temporary `sqlite+aiosqlite` and enter `lifespan` → `GET /health` returns HTTP `200` `HealthResponse(status="ok", session_backend="sqlite", cache_backend="memory", version="0.1.0")` with `X-Request-ID`; `GET /api/v1/markets` returns HTTP `200` `MarketsResponse` enumerating `EG`/`EGP`, `SA`/`SAR`, `AE`/`AED` with `noon` and `amazon` metadata (`backend/tests/integration/test_fastapi_endpoints.py::test_health_and_markets_endpoints`).
- [x] **T2.2 — `POST /api/v1/search` Offline Cache Miss -> Hit `< 300 ms` & `0` LLM Calls (`INV-04`, `NFR1`)**: Call `POST /api/v1/search` twice with `"سماعة أنكر"` (`country="EG"`) against `SeedCatalogProvider` + `InMemoryTTLCache` and an injected `FakeLLMClient` spy → `FakeLLMClient` call count stays `0`, first call returns HTTP `200` `SearchResponse(cache_hit=False, source_mode="seed")` with Top-3 `RankedOffer` sorted by `value_score`, and repeat call returns `cache_hit=True` with identical ranked offers and measured duration `< 300 ms` (`backend/tests/integration/test_fastapi_endpoints.py::test_search_endpoint_miss_then_hit_zero_llm_under_300ms`).
- [x] **T2.3 — `POST /api/v1/chat` Arabic/English Multi-Turn Flow (`search -> refine -> compare`)**: Exercise `POST /api/v1/chat` across Arabic initial query -> budget/store refinement using returned `session_id` -> `"قارن بين الأول والثاني"` (`COMPARE`) and an English flow using `create_app` + `FakeLLMClient` + `SeedCatalogProvider` + `SQLAlchemySessionRepository` (`sqlite+aiosqlite`) → verifies `status="ok"`, persisted session continuity, `COMPARE` executing `0` `CatalogProvider` calls, and unmodified `ProductOffer` grounding (`INV-05`) (`backend/tests/integration/test_fastapi_endpoints.py::test_chat_endpoint_bilingual_multiturn_search_refine_compare`).
- [x] **T2.4 — OpenAPI 3.1 Contract Verification (`/openapi.json`)**: Fetch `GET /openapi.json` → returns HTTP `200` with `openapi` starting with `"3.1"`, `info.version == "0.1.0"`, exact HTTP methods per path (`/api/v1/chat` `POST`, `/api/v1/search` `POST`, `/api/v1/markets` `GET`, `/health` `GET`), `422`/`429`/`503`/`500` error schema references to `#/components/schemas/ErrorResponse`, and component schemas/properties/enums for `ChatRequest`, `ChatResponse`, `SearchRequest`, `SearchResponse`, `MarketsResponse`, `HealthResponse`, and `ErrorResponse` (`backend/tests/integration/test_fastapi_endpoints.py::test_openapi_schema_contract_for_frontend_codegen`).

### Tier 3: Error & Edge-Case Verification

- [x] **T3.1 — `POST /api/v1/chat` Guardrail Refusal vs `422` Structural Validation (`D1`, `INV-09`)**: Send empty/whitespace message (`"   "`), oversized message (`> guardrail_max_chars`), prompt-injection text, and a Luhn payment card number (`"4111111111111111"`) to `POST /api/v1/chat` → returns HTTP `200` `ChatResponse(status="refused", action="refuse")` without persisting sensitive payload into prior session or invoking `LLMClient`; send structurally invalid payloads (missing `"message"`, `max_budget=-5`, unknown extra field, invalid `country`) → returns HTTP `422` `ErrorResponse(error_code="validation_error")` (`backend/tests/integration/test_fastapi_endpoints.py::test_chat_guardrail_refusal_vs_structural_422`).
- [x] **T3.2 — Upstream `CatalogProviderError` Handling (`/api/v1/chat` `degraded` vs `/api/v1/search` `503`)**: Inject a failing `CatalogProvider` raising `CatalogProviderError(provider="serper", retriable=True, reason="timeout")` → `POST /api/v1/chat` degrades cleanly to HTTP `200` `ChatResponse(status="degraded", top_offers=[], telemetry.degraded_reason=...)` (`INV-08`), whereas `POST /api/v1/search` returns HTTP `503` `ErrorResponse(error_code="catalog_unavailable", retriable=True, request_id=...)` (`backend/tests/integration/test_fastapi_endpoints.py::test_catalog_outage_chat_degrades_and_search_returns_503`).
- [x] **T3.3 — `POST /api/v1/search` Boundary & Validation Rejections (`422`)**: Submit `query=""`, `query="   "`, `query="a"*501`, `query` with control/bidi/Unicode-Tag chars, `max_budget=0`, `max_budget="1e50"`, `min_rating=5.5`, `country="US"`, and extra unknown field → all return HTTP `422` `ErrorResponse(error_code="validation_error", request_id=...)` (`backend/tests/integration/test_fastapi_endpoints.py::test_search_endpoint_422_validation_envelopes`).
- [x] **T3.4 — Rate Limit `429`, `Retry-After`, Trusted-Proxy `X-Forwarded-For` Hardening & Exemptions over HTTP**: Configure `rate_limit_rpm=2` on `create_app(...)` → untrusted peer ignores `X-Forwarded-For`; when peer is inside `trusted_proxy_cidrs`, right-to-left untrusted hop isolates distinct client buckets while malformed rightmost `X-Forwarded-For` falls back safely to peer host; 3rd `POST /api/v1/chat` or `POST /api/v1/search` returns HTTP `429` with `Retry-After` header, `X-Request-ID`, and `ErrorResponse(error_code="rate_limit_exceeded")`; `GET /health` and `GET /api/v1/markets` continue returning `200` even while rate-limited (`backend/tests/integration/test_fastapi_endpoints.py::test_http_rate_limiting_429_and_exemptions`).
- [x] **T3.5 — Lifespan DB Initialization Failure Fallback & Unhandled `500` Masking (`INV-01`, `INV-08`)**: Boot `create_app(AppSettings(database_url="postgresql+asyncpg://u:supersecret@127.0.0.1:1/db"))` entering `lifespan` → startup succeeds without crash, `GET /health` reports `status="degraded"` and `session_backend="memory"` with zero `"supersecret"` or raw DB URL strings, `POST /api/v1/chat` continues serving via `InMemorySessionStore`, and an injected unhandled `RuntimeError` returns HTTP `500` `ErrorResponse(error_code="internal_error")` with zero secrets or tracebacks (`backend/tests/integration/test_fastapi_endpoints.py::test_lifespan_db_fallback_and_500_error_masking`).

### Tier 4: Regression Checks

- [x] **T4.1 — Full Offline Backend Test Suite (`INV-07`)**: Run `uv run --directory backend pytest -v` → all Phase 1 and Phase 2 unit and integration tests pass 100% offline in `< 30 s` with zero skipped or relaxed assertions (`@pytest.mark.live` excluded by default).

### Tier 5: Build, Lint & Type Checks

- [x] **T5.1 — Ruff Lint Check**: `uv run --directory backend ruff check .` passes with zero errors.
- [x] **T5.2 — Ruff Format Check**: `uv run --directory backend ruff format --check .` passes with zero formatting diffs.
- [x] **T5.3 — Strict Mypy Type Check**: `uv run --directory backend mypy src` passes with zero type errors across `commerce_ai.main` and `commerce_ai.api.*`.
- [x] **T5.4 — Lockfile Integrity Check**: `uv lock --directory backend --check` passes cleanly without adding or changing dependencies (`P7`).

### Tier 6: Manual / Visual Verification

- **Status: Not Applicable**
- **Technical justification**: Feature 2.3 delivers a headless JSON `FastAPI` REST service with no frontend UI, browser layout, or Arabic `RTL` rendering; `Next.js` visual/RTL verification begins in Phase 3 (`Feature 3.1` and `Feature 3.2`).

### Tier 7: API / CLI / Application Checks

- [x] **T7.1 — ASGI Application Entrypoint & Live-In-Process Request Smoke Check**: Execute `uv run --directory backend python -c "..."` importing `commerce_ai.main:app`, running `lifespan` startup/shutdown, and issuing `httpx.AsyncClient(transport=ASGITransport(app=app))` calls to `GET /health`, `GET /api/v1/markets`, `POST /api/v1/search`, `POST /api/v1/chat`, and `GET /openapi.json` → asserts `200 OK` responses, valid `X-Request-ID`, and clean shutdown without exceptions.

### Extra Gates (from `spec/sdd-profile.md`)

- **Status: Not Applicable**
- **Technical justification**: Per `spec/sdd-profile.md`, `uv run --directory backend pytest tests/evals -v` becomes mandatory from Feature 4.1 onward once the golden Arabic/English evaluation dataset suite is introduced; Feature 2.3 validates all HTTP endpoints, contracts, middleware, and offline end-to-end flows through Tiers 1–5 and Tier 7.

---

## 4. Automated Execution Commands

```text
uv run --directory backend pytest tests/unit/test_api_middleware_and_schemas.py tests/integration/test_fastapi_endpoints.py -v
uv run --directory backend pytest -v
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy src
uv run --directory backend python -c "import asyncio, httpx; from commerce_ai.main import app; ..."
```

---

## 5. Execution Results (filled in execute mode)

| Check | Result (✅ / ❌ / ⏭ N/A) | Evidence (command output summary, counts) |
| :--- | :--- | :--- |
| `T1.1`–`T1.7` (Unit) | ✅ | `uv run --no-sync --directory backend pytest tests/unit/test_api_middleware_and_schemas.py tests/integration/test_fastapi_endpoints.py -v` → `16 passed, 1 warning in 6.64s` (7/7 unit tests in `test_api_middleware_and_schemas.py` passed) |
| `T2.1`–`T2.4` (Integration) | ✅ | Included in `16 passed, 1 warning in 6.64s` (`test_health_and_markets_endpoints`, `test_search_endpoint_miss_then_hit_zero_llm_under_300ms`, `test_chat_endpoint_bilingual_multiturn_search_refine_compare`, `test_openapi_schema_contract_for_frontend_codegen` all passed) |
| `T3.1`–`T3.5` (Error & Edge) | ✅ | Included in `16 passed, 1 warning in 6.64s` (`test_chat_guardrail_refusal_vs_structural_422`, `test_catalog_outage_chat_degrades_and_search_returns_503`, `test_search_endpoint_422_validation_envelopes`, `test_http_rate_limiting_429_and_exemptions`, `test_lifespan_db_fallback_and_500_error_masking` all passed) |
| `T4.1` (Regression) | ✅ | `uv run --no-sync --directory backend pytest -v` → `163 passed, 1 deselected, 1 warning in 18.37s` (`collected 164 items / 1 deselected / 163 selected`, 100% offline `< 30 s`, zero skipped or relaxed assertions) |
| `T5.1`–`T5.4` (Lint/Format/Type/Lock) | ✅ | `ruff check .` → `All checks passed!`; `ruff format --check .` → `62 files already formatted`; `mypy src` → `Success: no issues found in 43 source files`; `uv lock --directory backend --check` → `Resolved 70 packages in 2ms` |
| `Tier 6` (Manual / Visual) | ⏭ N/A | Headless JSON FastAPI API only; Next.js RTL UI starts in Phase 3 (`Feature 3.1`) |
| `T7.1` (API / ASGI Startup) | ✅ | `uv run --no-sync --directory backend python -c "..."` importing `commerce_ai.main:app` with `app.router.lifespan_context(app)` and `ASGITransport(app=app)` over `/health`, `/api/v1/markets`, `/api/v1/search`, `/api/v1/chat`, `/openapi.json` → `T7.1 OK: ok 3 3 ok 3.1.0` (all 5 endpoints `200 OK`, UUID4 `X-Request-ID`, clean shutdown) |
| `Extra Gates` (Evals) | ⏭ N/A | `tests/evals/` mandatory from Feature 4.1 onward per `spec/sdd-profile.md` |
