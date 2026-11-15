# Validation Criteria: Feature 2.1 — LLM Routing, Guardrails & Bilingual Intent Extraction

## 1. Success Definition

Feature 2.1 is complete when `backend/pyproject.toml` and `backend/uv.lock` declare and lock all Phase 2 dependencies cleanly without heavy LLM SDKs, all Phase 2 package `__init__.py` scaffolds import cleanly, all folded Phase 1 hardening items (`AppSettings` `model_dump`/`model_dump_json` URL redaction, `SearchIntent` Arabic orthographic folding + `catalog_cache_key()`/`normalized_cache_key()` split, and `CachedCatalogProvider` single-flight coalescing) and new Phase 2 domain/LLM/guardrail/intent contracts satisfy every functional and non-functional requirement (`R1`–`R15`, `NFR1`–`NFR4`) through passing offline tests (`tests/unit/test_config_and_models.py`, `tests/unit/test_llm_clients.py`, `tests/unit/test_guardrails_and_intent.py`, `tests/integration/test_cached_catalog.py`, and updated `catalog_cache_key()` assertions in `tests/integration/test_phase1_e2e.py`), `@pytest.mark.live` smoke coverage (`tests/integration/test_live_llm_smoke.py`) remains deselected by default, and `uv lock --directory backend --check`, `uv run --directory backend pytest -v`, `ruff check .`, `ruff format --check .`, and `mypy src` all pass with zero warnings or errors.

---

## 2. Requirement Traceability

| Requirement | Checks |
|:---|:---|
| R1 | T1.1, T5.1, T5.2, T5.3, T5.4 |
| R2 | T1.2, T3.1 |
| R3 | T1.3, T3.2 |
| R4 | T1.4, T3.3 |
| R5 | T1.5 |
| R6 | T2.1, T2.2, T3.4 |
| R7 | T1.6, T3.5 |
| R8 | T1.7, T3.5 |
| R9 | T1.8, T3.6 |
| R10 | T1.9 |
| R11 | T1.10, T3.7 |
| R12 | T1.11, T3.8, T3.9 |
| R13 | T1.12 |
| R14 | T1.13, T3.10, T3.11 |
| R15 | T1.14, T4.1 |
| NFR1 | T1.2, T1.6, T3.1, T3.5, T3.8 |
| NFR2 | T1.15, T5.4 |
| NFR3 | T1.8, T1.12, T2.1, T2.2, T4.1 |
| NFR4 | T5.1, T5.2, T5.3, T5.4 |

---

## 3. Verification Tiers

### Tier 1: Unit Verification
- [x] T1.1 — `pyproject.toml` declares all Phase 2 runtime deps (`fastapi`, `uvicorn`, `langgraph`, `sqlalchemy[asyncio]`, `aiosqlite`, `asyncpg`) with zero `litellm`/vendor SDKs, preserves `addopts = ["-m", "not live"]`, and imports all Phase 2 package scaffolds (`commerce_ai.agent`, `commerce_ai.adapters.llm`, `commerce_ai.adapters.session`, `commerce_ai.api`) cleanly (`tests/unit/test_config_and_models.py::test_package_scaffold_and_pyproject_contract`).
- [x] T1.2 — `AppSettings()` populates all Phase 2 defaults (`app_env`, `log_level`, `llm_mode`, `explain_mode`, `llm_primary_model`, `llm_fallback_model`, `llm_timeout_seconds`, `guardrail_max_chars`, `database_url`, `session_ttl_seconds`, `session_max_turns`, `cors_allowed_origins`, `rate_limit_rpm`), loads `backend/.env.example`, parses comma-separated and JSON `CORS_ALLOWED_ORIGINS` with inline `#` comments, masks secrets/URLs across `repr()`, `str()`, `model_dump()`, `model_dump_json()`, and `safe_summary()`, and preserves raw `settings.redis_url` / `settings.database_url` attributes (`tests/unit/test_config_and_models.py::test_app_settings_defaults_and_env_loading`).
- [x] T1.3 — `SearchIntent` applies Arabic orthographic folding (`أ/إ/آ/ٱ -> ا`, `ة -> ه`, `ى -> ي`), emits `catalog_cache_key()` (`"{country}:{store}:{language}:{slug}"`), and emits updated `normalized_cache_key()` (`"{country}:{store}:{language}:{slug}:{budget}:{min_rating}"`) identically across orthographic and whitespace variants (`tests/unit/test_config_and_models.py::test_search_intent_normalized_cache_key`).
- [x] T1.4 — Phase 2 enums (`TurnAction`, `TurnStatus`) and models (`LLMMessage`, `LLMRequest`, `LLMResponse`, `SessionTurn`, `SessionState`, `TurnTelemetry`, `ChatTurnResult`) instantiate with expected defaults and round-trip cleanly through JSON (`SessionState` preserving verified Google Shopping links with cache context) (`tests/unit/test_config_and_models.py::test_phase2_domain_models_and_enums`).
- [x] T1.5 — `LLMProviderError(provider, retriable, reason)` and `SessionStoreError` inherit from `DomainError`, and `@runtime_checkable` `LLMClient` and `SessionRepository` protocols (`domain/ports.py`) structurally match valid doubles (`tests/unit/test_config_and_models.py::test_phase2_errors_and_ports`).
- [x] T1.6 — `GeminiLLMClient` sends `POST .../models/{model_id}:generateContent` with `x-goog-api-key` header (zero key in URL query string), `systemInstruction`, `contents`, `maxOutputTokens`, `temperature`, and `responseMimeType="application/json"` via `httpx.MockTransport` and returns parsed `LLMResponse` (`tests/unit/test_llm_clients.py::test_gemini_client_request_and_response`).
- [x] T1.7 — `OpenAICompatibleLLMClient` sends `POST {base_url}/chat/completions` for `groq` (`api.groq.com/openai/v1`), `openai` (`api.openai.com/v1`), and custom `base_url` with `Authorization: Bearer ...` and `response_format={"type": "json_object"}` via `httpx.MockTransport` and parses `LLMResponse` (`tests/unit/test_llm_clients.py::test_openai_compatible_client_request_and_response`).
- [x] T1.8 — `ModelRouterLLMClient` succeeds on `primary` with zero fallback call, and on primary `LLMProviderError` fails over strictly once to `fallback` returning `used_fallback_model=True` (`tests/unit/test_llm_clients.py::test_model_router_primary_and_single_failover`).
- [x] T1.9 — `FakeLLMClient` returns scripted responses or handler results offline with zero network calls and records `requests` and `call_count` accurately (`tests/unit/test_llm_clients.py::test_fake_llm_client_records_requests`).
- [x] T1.10 — `create_llm_client` resolves `"fake"` -> `FakeLLMClient`, `"auto"` with keys -> routed live client, `"auto"` without keys -> `None`, and `"live"` with keys -> live client (`tests/unit/test_llm_clients.py::test_create_llm_client_modes`).
- [x] T1.11 — `check_input_guardrails` allows clean Arabic/English shopping queries with budgets, model codes, and non-Luhn SKUs, returning `allowed=True`, `sanitized_message`, and detected `language` (`tests/unit/test_guardrails_and_intent.py::test_guardrails_allow_legitimate_shopping_queries`).
- [x] T1.12 — `extract_turn_intent` with `FakeLLMClient` issues 1 `LLMRequest` (`max_tokens <= 350`, `json_mode=True`), classifies `SEARCH`/`COMPARE`/`CLARIFY`/`OFF_TOPIC`, extracts `SearchIntent`, merges `prior_intent` deltas on follow-ups, and enforces `store_override` / `max_budget_override` / `language_hint` (`tests/unit/test_guardrails_and_intent.py::test_extract_turn_intent_with_llm_and_delta_merging`).
- [x] T1.13 — `extract_turn_intent` with `llm_client=None` deterministically parses Arabic & English queries, Arabic-Indic numerals (`٠١٢٣٤٥٦٧٨٩`), country/store hints (`مصر`/`السعودية`/`الإمارات`, `نون`/`أمازون`), budgets, ratings, accessory queries, `COMPARE`, `CLARIFY`, `OFF_TOPIC`, and follow-up delta refinements (`tests/unit/test_guardrails_and_intent.py::test_rule_based_bilingual_intent_parser`).
- [x] T1.14 — `tests/integration/test_live_llm_smoke.py` exists with `@pytest.mark.live` marker and is automatically deselected during default `pytest` runs (`tests/unit/test_llm_clients.py::test_live_smoke_marker_registered_and_deselected`).
- [x] T1.15 — AST import check confirms `commerce_ai.config`, `commerce_ai.domain`, and Feature 2.1 `commerce_ai.agent` (`guardrails.py`, `intent.py`) import zero HTTP/DB/API/LLM vendor SDKs (`httpx`, `redis`, `serper`, `langfuse`, `boto3`, `sqlalchemy`, `fastapi`, `litellm`, `openai`, `groq`, `google`) (`tests/unit/test_config_and_models.py::test_hexagonal_boundary_no_vendor_imports`).

### Tier 2: Integration Verification
- [x] T2.1 — `CachedCatalogProvider` + `SeedCatalogProvider` / `SerperShoppingProvider` (`MockTransport`) + `InMemoryTTLCache` / `fakeredis` keys entries by `intent.catalog_cache_key()`, serving budget/min_rating refinements and Arabic orthographic variants with `cache_hit=True` and 0 duplicate upstream calls while separating `"ar"` vs `"en"` cache entries (`tests/integration/test_cached_catalog.py::test_cached_catalog_key_reuse_and_language_isolation`, plus updated `catalog_cache_key()` TTL/key assertions in `tests/integration/test_phase1_e2e.py`).
- [x] T2.2 — Concurrent `asyncio.gather` calls to `CachedCatalogProvider.search_offers()` on an identical cold `catalog_cache_key()` coalesce via `_in_flight` so the underlying provider executes strictly 1 call, all concurrent callers receive valid results, and cancelling one waiter does not abort the remaining waiters (`tests/integration/test_cached_catalog.py::test_cached_catalog_single_flight_coalescing`).

### Tier 3: Error & Edge-Case Verification
- [x] T3.1 — `AppSettings` masks passwords in `redis_url` and `database_url` inside `model_dump()`, `model_dump_json()`, `repr()`, `str()`, and `safe_summary()`, normalizes blank optional keys/fallback model to `None`, and rejects invalid bounds (`guardrail_max_chars`, `session_max_turns`, `rate_limit_rpm`, blank `database_url`/`llm_primary_model`) (`tests/unit/test_config_and_models.py::test_app_settings_secret_masking_and_invalid_values`).
- [x] T3.2 — `SearchIntent` separates `"ar"` vs `"en"` in `catalog_cache_key()`/`normalized_cache_key()` and collapses `أ/إ/آ/ٱ -> ا`, `ة -> ه`, `ى -> ي` consistently alongside punctuation-only SHA-256 fallback slugs (`tests/unit/test_config_and_models.py::test_search_intent_validation_edge_cases`).
- [x] T3.3 — Phase 2 domain models reject invalid bounds (`LLMRequest.messages` empty, `max_tokens > 1024`, `TurnTelemetry.llm_calls > 2`, extra fields via `extra="forbid"`) (`tests/unit/test_config_and_models.py::test_phase2_models_reject_invalid_bounds`).
- [x] T3.4 — Concurrent `CachedCatalogProvider.search_offers()` calls on a failing provider coalesce onto 1 upstream call, clean up `_in_flight` in `finally`, propagate `CatalogProviderError` to callers without caching the error, and allow the next call to recover cleanly (`tests/integration/test_cached_catalog.py::test_cached_catalog_single_flight_error_cleanup`).
- [x] T3.5 — `GeminiLLMClient` and `OpenAICompatibleLLMClient` map `httpx.TimeoutException`, transport errors, `429`/`5xx` (retriable), `401`/`400` (non-retriable), and malformed JSON payloads into `LLMProviderError` while strictly redacting API keys from error messages (`tests/unit/test_llm_clients.py::test_llm_clients_error_classification_and_secret_redaction`).
- [x] T3.6 — `ModelRouterLLMClient` propagates `LLMProviderError` cleanly when `fallback=None` or when both `primary` and `fallback` fail (`tests/unit/test_llm_clients.py::test_model_router_exhaustion_raises_provider_error`).
- [x] T3.7 — `create_llm_client` raises `LLMProviderError(provider="llm", retriable=False, ...)` when `llm_mode="live"` lacks any valid API key or configures an unsupported provider prefix (`tests/unit/test_llm_clients.py::test_create_llm_client_live_missing_key_raises`).
- [x] T3.8 — `check_input_guardrails` blocks Luhn-valid 13–19 digit payment cards (ASCII and Arabic-Indic digits), CVVs, passwords/PINs, and national IDs at 0 tokens with `reason_code="sensitive_pii_payment"` and `sanitized_message=""` without echoing sensitive input (`tests/unit/test_guardrails_and_intent.py::test_guardrails_block_payment_and_pii_payloads`).
- [x] T3.9 — `check_input_guardrails` blocks empty/whitespace strings, inputs `> max_chars`, control/bidi-override characters, and bilingual Arabic/English prompt-injection & system-prompt extraction phrases (`tests/unit/test_guardrails_and_intent.py::test_guardrails_block_length_control_and_prompt_injection`).
- [x] T3.10 — `extract_turn_intent` falls back automatically to the deterministic rule parser when `llm_client` raises `LLMProviderError`, returns non-JSON text, or violates schema, setting `used_rule_fallback=True` and `degraded_reason` (`tests/unit/test_guardrails_and_intent.py::test_extract_turn_intent_falls_back_on_llm_error_or_bad_json`).
- [x] T3.11 — `extract_turn_intent` handles edge inputs: switching to a completely new product clears stale `prior_intent.max_budget`, underspecified queries return `CLARIFY` with localized prompt, and non-shopping queries return `OFF_TOPIC` (`tests/unit/test_guardrails_and_intent.py::test_extract_turn_intent_edge_cases`).

### Tier 4: Regression Checks
- [x] T4.1 — Full backend suite (including updated `tests/integration/test_phase1_e2e.py` `catalog_cache_key()` assertions) runs cleanly 100% offline (`-m "not live"`) in `< 30 s` with zero skipped assertions: `uv run --directory backend pytest -v` (`INV-07`).

### Tier 5: Build, Lint & Type Checks
- [x] T5.1 — Lockfile & dependency sync succeeds: `uv sync --directory backend --all-extras --dev` and `uv lock --directory backend --check`.
- [x] T5.2 — Ruff lint passes with zero errors: `uv run --directory backend ruff check .`.
- [x] T5.3 — Ruff format check passes with zero diffs: `uv run --directory backend ruff format --check .`.
- [x] T5.4 — Strict mypy passes with zero errors: `uv run --directory backend mypy src`.

### Tier 6: Manual / Visual Verification
- **Status: Not Applicable**
- **Technical justification**: Feature 2.1 delivers backend dependency locking, configuration, domain schemas/ports, LLM adapters, and agent guardrails/intent extraction with zero UI or browser rendering; Arabic `RTL` Next.js verification starts in Phase 3 (`Feature 3.1`).

### Tier 7: API / CLI / Application Checks
- **Status: Not Applicable**
- **Technical justification**: Feature 2.1 introduces internal Python adapters and agent modules only with no HTTP endpoints or `uvicorn` entrypoint; FastAPI route and startup checks (`/health`, `/api/v1/markets`, `/api/v1/search`, `/api/v1/chat`) land in Phase 2 `Feature 2.3`.

### Extra Gates
- **Status: Not Applicable**
- **Technical justification**: Per `spec/sdd-profile.md`, `uv run --directory backend pytest tests/evals -v` becomes mandatory from `Feature 4.1` onward once the full `LangGraph` recommendation workflow and golden Arabic/English evaluation dataset exist.

---

## 4. Automated Execution Commands

```text
uv sync --directory backend --all-extras --dev
uv lock --directory backend --check
uv run --directory backend pytest tests/unit/test_config_and_models.py tests/unit/test_llm_clients.py tests/unit/test_guardrails_and_intent.py tests/integration/test_cached_catalog.py -v
uv run --directory backend pytest -v
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy src
```

---

## 5. Execution Results (filled in execute mode)

| Check | Result (✅ / ❌ / ⏭ N/A) | Evidence (command output summary, counts) |
|:---|:---|:---|
| Dependency sync (`uv sync --directory backend --all-extras --dev`) | ✅ | Synced `backend/.venv` with Phase 2 dependencies in `backend/pyproject.toml` and updated `backend/uv.lock` (exit code `0`) |
| Lockfile consistency (`uv lock --directory backend --check`) | ✅ | `Resolved 70 packages in 2ms` (exit code `0`) |
| Feature 2.1 + Folded Phase 1 suites (`uv run --no-sync --directory backend pytest tests/unit/test_config_and_models.py tests/unit/test_llm_clients.py tests/unit/test_guardrails_and_intent.py tests/integration/test_cached_catalog.py tests/integration/test_phase1_e2e.py -v`) | ✅ | `64 passed in 1.29s` (`0` failed, `0` skipped; covers `T1.1`–`T1.15`, `T2.1`–`T2.2`, `T3.1`–`T3.11`) |
| Full offline backend suite (`uv run --no-sync --directory backend pytest -v`) | ✅ | `collected 103 items / 1 deselected / 102 selected`; `102 passed, 1 deselected in 1.83s` (`0` failed, `0` skipped; `@pytest.mark.live` deselected by default `addopts = ["-m", "not live"]`) (`T4.1`, `INV-07`) |
| Live opt-in smoke collection/guard (`uv run --no-sync --directory backend pytest tests/integration/test_live_llm_smoke.py -m live -v`) | ✅ | `1 skipped in 0.24s` (explicitly opt-in via `-m live`; skips cleanly when no live provider API keys are configured) |
| Ruff lint (`uv run --no-sync --directory backend ruff check .`) | ✅ | `All checks passed!` (exit code `0`, `T5.2`) |
| Ruff format (`uv run --no-sync --directory backend ruff format --check .`) | ✅ | `44 files already formatted` (exit code `0`, `T5.3`) |
| Strict type check (`uv run --no-sync --directory backend mypy src`) | ✅ | `Success: no issues found in 31 source files` (exit code `0`, `T5.4`) |
| Tier 6 — Manual / Visual UI | ⏭ N/A | Backend-only feature; no UI or browser rendering until Phase 3 (`Feature 3.1`) |
| Tier 7 — API / CLI / Application | ⏭ N/A | Internal Python adapters/agent modules only; FastAPI routes and startup checks land in `Feature 2.3` |
| Extra Gates — Eval suite (`tests/evals`) | ⏭ N/A | Eval dataset and full LangGraph workflow checks begin in Phase 4 (`Feature 4.1`) |
