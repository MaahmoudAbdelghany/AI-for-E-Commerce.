# Post-Validation Review: Phase 2 — Bounded LangGraph Shopping Agent, Model Routing & FastAPI Service

- **Phase**: `phase-2-agent-and-api`
- **Branch**: `phase/2-agent-and-api` (vs `main` at `03dc338`)
- **Status**: `APPROVED` (Phase Gate 2 approved by human on 2026-11-15; merged into `main` via `--no-ff` at `48fa64e`)
- **Commit range (`main..HEAD`)**: `42ae69b..9b4ad0c` (`7` local commits; `65 files changed, 14884 insertions(+), 142 deletions(-)`)

## Chronological Commit History (`git log --oneline main..HEAD`)

1. `42ae69b` — `docs(spec): add Phase 2 specs`
2. `565f0da` — `feat(agent): implement Feature 2.1 LLM routing, guardrails, and bilingual intent extraction`
3. `c19e663` — `fix(deps): declare sqlalchemy[asyncio] extra for async session runtime`
4. `2d245b9` — `feat(workflow): implement Feature 2.2 bounded LangGraph workflow and session memory`
5. `4a78301` — `feat(api): implement Feature 2.3 FastAPI service, middleware, and REST contracts`
6. `ce3387b` — `test(phase-2): add end-to-end phase integration tests and PI evidence`
7. `9b4ad0c` — `fix(phase-2): resolve security, architecture, spec-drift, and test review findings`

---

## 1. Scope & Backlog Disposition

- **Delivered Features**:
  - **Feature 2.1 (`spec/features/feature-201-llm-routing-guardrails-intent/`)**: Upfront Phase 2 runtime dependencies & package `__init__.py` scaffolds (`P7`), folded Phase 1 hardening (`P1`), async `httpx` multi-provider `LLMClient` routing (`GeminiLLMClient`, `OpenAICompatibleLLMClient`, `ModelRouterLLMClient`, `FakeLLMClient`, `create_llm_client` — `P2`), zero-token pre-LLM guardrails (`check_input_guardrails` — `P3`), bilingual (`ar`/`en`) intent extraction with rule-based fallback (`extract_turn_intent` — `P3`), and opt-in `@pytest.mark.live` smoke coverage (`P8`).
  - **Feature 2.2 (`spec/features/feature-202-langgraph-workflow-and-session/`)**: Bounded `LangGraph` `StateGraph` (`ShoppingAssistantWorkflow` capped at `<= 2` LLM calls/turn, smart adaptive `explain`, multi-turn refinements, zero-catalog `COMPARE`, `P4`), grounded Call #2 prompts (`prompts.py`), zero-token bilingual templates (`templates.py`), and async session memory (`InMemorySessionStore`, `SQLAlchemySessionRepository` over `sqlite+aiosqlite` / `postgresql+asyncpg` with `Base.metadata.create_all` auto-init, `ResilientSessionRepository` automatic fallback & 30 s cooldown recovery, `P5`).
  - **Feature 2.3 (`spec/features/feature-203-fastapi-service-and-contracts/`)**: Versioned OpenAPI 3.1 `FastAPI` REST service (`POST /api/v1/chat`, 0-LLM `POST /api/v1/search`, `GET /api/v1/markets`, secret-free `GET /health`), async `lifespan` sharing one `httpx.AsyncClient`, `RequestIDMiddleware`, `CORSMiddleware`, trusted-proxy `X-Forwarded-For` sliding-window rate limiter (`429` + `Retry-After`), and unified secret-scrubbed `ErrorResponse` envelopes (`P6`).
- **Folded Phase 1 Backlog (`P1`)**: All 3 items in [`spec/backlog/2026-11-15-phase1-cache-and-settings-followups.md`](../../backlog/2026-11-15-phase1-cache-and-settings-followups.md) are **Done** (implemented in Feature 2.1, verified in `9b4ad0c`, and updated to `Done (Implemented in Phase 2 — Feature 2.1)` across the backlog item, [`spec/backlog/README.md`](../../backlog/README.md), [`spec/roadmap.md`](../../roadmap.md), and amended `feature-101` / `feature-103` specs):
  1. `AppSettings` `@field_serializer("redis_url", "database_url", when_used="always")` calling `redact_url_password(...)` for `model_dump()` and `model_dump_json()`.
  2. `SearchIntent` Arabic orthographic folding (`أ/إ/آ/ٱ -> ا`, `ة -> ه`, `ى -> ي`, plus Arabic-Indic digits `٠-٩`/`۰-۹ -> 0-9`), upstream `catalog_cache_key()` (`{country}:{store}:{language}:{slug}`), and language-aware `normalized_cache_key()`.
  3. `CachedCatalogProvider.search_offers()` per-key `asyncio.Lock` + `_in_flight` single-flight coalescing (shielded awaits, `finally` cleanup, zero error caching).
- **Newly Captured Phase 4 Backlog**: Created [`spec/backlog/2026-11-15-phase2-post-llm-and-distributed-rate-limit-followups.md`](../../backlog/2026-11-15-phase2-post-llm-and-distributed-rate-limit-followups.md) (`Status: Open`) to track two out-of-scope hardening items for Phase 4 without blocking Phase 2 Gate 2:
  1. Redis-backed distributed sliding-window rate limiting + edge AWS WAF limiting (`Feature 4.2`).
  2. Lightweight post-LLM output prose validation for unverified URLs/prompt-leakage markers on `ChatResponse.reply` / `clarification_question` (`Feature 4.1`; `top_offers` remains strictly verified per `INV-05`).
- **Sensitive Area & Workspace Boundary Audit**:
  - `git diff --name-only main..HEAD` touches **0** files in `spec/sdd-profile.md` Sensitive Areas (`infra/aws/**`, `.github/workflows/**`, `backend/src/commerce_ai/config/security*`, `backend/migrations/**`), **0** files in `frontend/`, **0** edits to `CHANGELOG.md`, `backend/.env.example`, or constitution docs (`spec/architecture.md`, `spec/tech.md`, `spec/sdd-profile.md`).
  - Pre-existing unstaged modification `M .agents/skills/my_method_for_explaining/SKILL.md` in `git status --short` remains untouched and outside all Phase 2 commits.

---

## 2. The 5 Core Review Questions

| # | Question | Verdict | Evidence |
|:---|:---|:---|:---|
| 1 | Does it work, and is every requirement (`Feature 2.1` `R1`–`R15`, `Feature 2.2` `R1`–`R13`, `Feature 2.3` `R1`–`R10`, NFRs, `INV-01`–`INV-09`, `P1`–`P8`) satisfied? | ✅ | Every functional requirement, NFR, constraint, and Phase 2 decision (`P1`–`P8`) maps bidirectionally across `spec/features/feature-20{1,2,3}-*/{requirements,validation}.md` and passes in verified code and tests (`163` offline tests + `1` deselected `@pytest.mark.live` + Tier 7 ASGI smoke `T7.1 OK`). |
| 2 | Is the diff free of unapproved scope, dead code, secrets, or sensitive-area edits (`git diff main..HEAD`)? | ✅ | `git diff --stat main..HEAD` touches `65` scoped files (`2` manifest/lock, `31` `backend/src/commerce_ai/**` modules, `12` `backend/tests/**` files, `20` `spec/` files). `ruff check .` passes cleanly (`All checks passed!`), zero hardcoded secrets or `.env` files exist, `0` Sensitive Area paths were touched, and pre-existing `.agents/skills/my_method_for_explaining/SKILL.md` remains untouched. |
| 3 | Are all validation checks genuinely passing (offline suite, Tier 7 ASGI smoke, `ruff`, `mypy src`, `uv lock --check`)? | ✅ | Independent `verifier` re-run (`#65`) on final `9b4ad0c` code passed: `163 passed, 1 deselected, 1 warning in 17.22s` (`0` failed, `0` skipped, `< 30 s`; deselected is `@pytest.mark.live` `test_live_llm_smoke.py`), per-feature subsets (`65` / `31` / `16` / `13`), `-m live` (`1 skipped in 0.20s`), `T7.1 OK: ok 3 3 ok 3.1.0`, `ruff check .`, `ruff format --check .` (`62 files already formatted`), `mypy src` (`43 source files`), and `uv lock --check` (`70 packages`). |
| 4 | Are `spec/` files in sync with the code? | ✅ | Phase 1 amended specs (`feature-101`, `feature-103`), Phase 2 specs (`feature-201`–`203` `{plan,requirements,validation}.md`), `phase-overview.md`, `spec/roadmap.md`, and `spec/backlog/` are fully synced (`9b4ad0c` + Gate 2 `phase-overview.md` update). Two low constitution wording items in `spec/architecture.md`/`spec/tech.md`/`spec/sdd-profile.md` (unverified Phase 1 command tags in `sdd-profile.md`; Phase 0 placeholder names in `architecture.md:61,75,79` & `tech.md:14`) remain intentionally untouched before Gate 2 and are explicitly queued for post-Gate-2 `sdd-replan` Mode D. |
| 5 | Are error handling, resilience, guardrails, hexagonal boundaries, and secret-free logging clean? | ✅ | AST tests prove zero vendor SDK imports in `config/`, `domain/`, `agent/` (`INV-02`), and no direct adapter/DB/LLM HTTP logic in `api/` routes. `AppSettings` redacts keys/URLs in `repr()`/`str()`/`model_dump()`/`model_dump_json()`/`safe_summary()`; `GeminiLLMClient` sends `x-goog-api-key` headers; `check_input_guardrails` short-circuits `NFKD`+`Cf`/`Mn`/tatweel/Unicode-Tag/Luhn inputs at `0` DB/LLM calls (`INV-09`); `CatalogProviderError`, `LLMProviderError`, and `SessionStoreError` degrade cleanly (`TurnStatus.DEGRADED`, `503`/`429`/`422`/`500` scrubbed `ErrorResponse`, rule/template fallback, `SQLAlchemy` -> `InMemorySessionStore` with 30 s recovery, `INV-01`/`INV-08`). |

### Per-Feature Verdict Summary

| Scope Item | Spec Status | Verdict | Key Evidence (`#65` / `9b4ad0c`) |
|:---|:---|:---|:---|
| **Feature 2.1** — LLM Routing, Guardrails, Bilingual Intent & Folded Phase 1 `P1` | `Committed` (`plan.md`), `✅ Done` | ✅ Pass | `65 passed in 1.18s` (`test_config_and_models.py` `25`, `test_llm_clients.py` `9`, `test_guardrails_and_intent.py` `7`, `test_cached_catalog.py` `8`, `test_phase1_e2e.py` `16`); `1 skipped` (`-m live`) |
| **Feature 2.2** — Bounded `LangGraph` Workflow & Async Session Memory | `Committed` (`plan.md`), `✅ Done` | ✅ Pass | `31 passed, 1 warning in 5.66s` (`test_session_stores.py` `9`, `test_agent_graph.py` `17`, `test_langgraph_session.py` `5`) |
| **Feature 2.3** — Versioned `FastAPI` Service, Middleware & REST Contracts | `Committed` (`plan.md`), `✅ Done` | ✅ Pass | `16 passed, 1 warning in 6.94s` (`test_api_middleware_and_schemas.py` `7`, `test_fastapi_endpoints.py` `9`) + Tier 7 `T7.1 OK: ok 3 3 ok 3.1.0` |
| **Phase Integration (`PI.1`–`PI.3`)** & Deep Review Fixes | `Validated` (`phase-overview.md`) | ✅ Pass | `13 passed, 1 warning in 6.94s` (`test_phase2_e2e.py`); `163 passed, 1 deselected, 1 warning in 17.22s` full suite; `ruff`, `mypy src`, `uv lock --check` clean |

---

## 3. 4-Lens Deep Review Results & Finding Dispositions

Four parallel read-only review lenses audited the phase diff (`#56`–`#59`) prior to remediation commit `9b4ad0c`. All **2 High** and **11 Medium** findings were resolved (with `1` multi-instance distributed rate-limiter component split cleanly to Phase 4 backlog after fixing trusted-proxy `X-Forwarded-For` handling in `9b4ad0c`) and independently verified in `#65` (`0` open High or Medium blockers).

| Lens & Source | Finding | Severity | Disposition & Verification |
|:---|:---|:---|:---|
| **Lens 1: Security & Governance (`#57`)** | Zero-width/invisible Unicode (`Cf`) & combining-mark (`Mn`) / Unicode Tag obfuscation bypassed `check_input_guardrails` (`agent/guardrails.py`, `INV-09`). | **High** | **Fixed in `9b4ad0c`** (verified `#65`): rejected Unicode Tags `U+E0000..U+E007F`, stripped Unicode `Cf`/`Mn` & tatweel in normalization and `Cf` in `sanitized_message`; added regression tests & synced `feature-201`. |
| **Lens 1 (`#57`)** | Unbounded `Decimal` exponent in `max_budget` (e.g. `"1e50"`) raised `decimal.InvalidOperation` (`500`), bypassed `_apply_overrides`, and poisoned persisted sessions. | **Medium** | **Fixed in `9b4ad0c`** (verified `#65`): enforced `max_budget <= Decimal("10000000.00")` in `ChatRequest`/`SearchRequest`/`SearchIntent`, caught `InvalidOperation` in `models.py`/`intent.py`/`sqlalchemy_repo.py`, validated overrides via `model_validate`; synced `feature-201`/`203` & tests. |
| **Lens 1 (`#57`) & Lens 2 (`#56`)** | Rate limiter unconditionally trusted leftmost `X-Forwarded-For` header from any peer (`api/middleware.py`). | **Medium** | **Fixed in `9b4ad0c`** (verified `#65`): added `AppSettings.trusted_proxy_cidrs` (`["127.0.0.1/32", "::1/128"]`) and parsed right-to-left untrusted hops only for trusted peers; synced `feature-201`/`203`, `phase-overview.md`, and tests. |
| **Lens 1 (`#57`)** | `SearchRequest.query` allowed control/bidi chars; `check_input_guardrails` scanned full string before `max_chars` & skipped dot-separated Luhn cards; `_QUERY_SECRET_RE` omitted `passwd`/`pwd`/`secret`/`api_key` in config/DB/Redis scrubbers. | **Low** | **Fixed in `9b4ad0c`** (verified `#65`): rejected control/bidi/Tag chars on `SearchRequest.query`, checked `len(message) > max_chars` first (`message[:max_chars]` for language), added dot-Luhn support, and aligned `_QUERY_SECRET_RE` across `settings.py`, `sqlalchemy_repo.py`, `redis_store.py`, and `api/errors.py`. |
| **Lens 1 (`#57`)** | Post-LLM prose validation (unverified URL / prompt-leakage filtering) absent on `ChatResponse.reply` / `clarification_question` (`top_offers` already strictly grounded per `INV-05`). | **Low** | **Deferred to Phase 4 backlog**: captured in [`spec/backlog/2026-11-15-phase2-post-llm-and-distributed-rate-limit-followups.md`](../../backlog/2026-11-15-phase2-post-llm-and-distributed-rate-limit-followups.md) #2 (`Status: Open`, Feature 4.1). |
| **Lens 2: Architecture, Scalability & Cost Control (`#56`)** | `SQLAlchemySessionRepository` used non-atomic `session.merge()` (concurrent first-turn `IntegrityError` race) and `ResilientSessionRepository` flipped permanently process-wide on any `SessionStoreError` without closing `_primary` or recovering. | **High** | **Fixed in `9b4ad0c`** (verified `#65`): replaced with dialect-native `ON CONFLICT (session_id) DO UPDATE`, enabled SQLite `WAL` + `busy_timeout=5000`, isolated per-row `IntegrityError`/`DataError`, added `30.0s` cooldown recovery probe, and disposed `_primary` on startup failure. |
| **Lens 2 (`#56`)** | `explain_mode="auto"` still invoked LLM Call #2 after Call #1 failed with `LLMProviderError` (`agent/graph.py`). | **Medium** | **Fixed in `9b4ad0c`** (verified `#65`): skipped Call #2 to template under `explain_mode="auto"` when `degraded_reasons` records `llm_provider_error:`; updated `test_agent_graph.py`, `test_phase2_e2e.py`, and `feature-202`. |
| **Lens 2 (`#56`)** | `main.py` lacked shared lifespan `httpx.AsyncClient` pooling & discarded initial defaults without closing; `ModelRouterLLMClient.aclose()` did not guard `_fallback` if `_primary.aclose()` raised. | **Medium** | **Fixed in `9b4ad0c`** (verified `#65`): shared one lifespan-owned `httpx.AsyncClient` across owned catalog/LLM factories, closed replaced default resources cleanly, and guarded `ModelRouterLLMClient.aclose()` via `try ... finally`. |
| **Lens 2 (`#56`)** | `commerce_sessions` table lacked periodic expired-row cleanup, and `create_async_engine` omitted explicit `asyncpg`/`aiosqlite` connect/command timeouts. | **Medium** | **Fixed in `9b4ad0c`** (verified `#65`): added throttled cleanup (`cleanup_interval_seconds=60.0`) and explicit `connect_args` timeouts (`aiosqlite` `3.0s`, `asyncpg` `2.0s`/`5.0s`); synced `feature-202` (`plan.md:132`, `requirements.md` R2). |
| **Lens 2 (`#56`)** | Process-local rate limiter buckets scale RPM across multi-worker containers (`N * rate_limit_rpm` in App Runner/ECS). | **Medium** | **Deferred to Phase 4 backlog** (after XFF fix in `9b4ad0c`): Redis-backed distributed sliding-window rate limiter + AWS WAF edge rule tracked in [`spec/backlog/2026-11-15-phase2-post-llm-and-distributed-rate-limit-followups.md`](../../backlog/2026-11-15-phase2-post-llm-and-distributed-rate-limit-followups.md) #1 (`Status: Open`, Feature 4.2). |
| **Lens 2 (`#56`)** | `CachedCatalogProvider` had a post-`cache.get()` TOCTOU window, and `SearchIntent._query_slug()` omitted Arabic-Indic digit folding (`٠-٩`/`۰-۹ -> 0-9`). | **Low** | **Fixed in `9b4ad0c`** (verified `#65`): added per-key `asyncio.Lock` over `cache.get` + `_in_flight` lookup/write/cleanup and Arabic-Indic digit folding in `SearchIntent`; synced `feature-201` & tests. |
| **Lens 2 (`#56`)** | Import-time `app = create_app()` in `main.py` allocates default `AsyncEngine` on import; `check_input_guardrails` scanned before `max_chars`. | **Low** | **Guardrail pre-scan fixed in `9b4ad0c`; `main.py` `app = create_app()` accepted**: module-level `app` is explicitly required by `feature-203` `R1` for `uvicorn commerce_ai.main:app` and Tier 7 `T7.1`. |
| **Lens 3: Spec Drift (`#59`)** | Folded Phase 1 backlog & amended `feature-101`/`feature-103` specs remained marked `Scheduled`/`⏳ Pending`/unchecked `[ ]`, and `feature-103/validation.md` `T2.1` cited `normalized_cache_key()`. | **Medium** | **Fixed in `9b4ad0c`** (verified `#65`): backlog set to `Done`, `feature-101` & `feature-103` checks (`T1.12`–`T1.13`, `T3.12`–`T3.13`, `T2.4`–`T2.5`, `T3.11`) ticked `[x]` with exact test paths, and `T2.1` updated to `catalog_cache_key()`. |
| **Lens 3 (`#59`)** | `test_phase2_e2e.py` (`test_e2e_guardrail_rejection_zero_db_zero_llm_calls`) failed non-deterministically on `"732" not in res.text` (colliding with random UUID4 `request_id` / `latency_ms` decimals). | **Medium** | **Fixed in `9b4ad0c`** (verified `#63`–`#65`): fixed deterministic `X-Request-ID` and popped `telemetry.latency_ms` from parsed JSON before substring check (`test_phase2_e2e.py:702-709`). |
| **Lens 3 (`#59`)** | `phase-overview.md` `Status` header remained `Implementing`, §2 rows mixed `Done`/`Committed`, and §5/§7 timings varied across runs. | **Medium** | **Fixed across `9b4ad0c` & Gate 2 finalization**: §2 rows standardized to `✅ Done` in `9b4ad0c`; `phase-overview.md` finalized here with `- **Status**: Validated`, `#65` verified timings, and final §7 Execution Log bullets. |
| **Lens 3 (`#59`)** | `domain/__init__.py` absent from `feature-201/plan.md` & `phase-overview.md` Expected Files; `render_refused_message` omitted `reason_code` in `feature-202/plan.md`; minor `validation.md` command/warning drift (`feature-201`, `feature-203`); `spec/roadmap.md:20` lacked backlog link. | **Low** | **Fixed in `9b4ad0c`** (verified `#65`, plus `SQLAlchemySessionRepository(..., cleanup_interval_seconds=60.0)` synced in `feature-202/plan.md:132` per `#63`/`#64`). |
| **Lens 3 (`#59`)** | Two low constitution wording items: (1) `spec/sdd-profile.md` backend commands still carry `(unverified — greenfield target)` tags; (2) `spec/architecture.md:61,75,79` & `spec/tech.md:14` retain Phase 0 placeholder names (`EG:noon:anker-bluetooth-earbuds`, `filter_and_rank_top_k`, `ChatResponse(summary, top_3_offers, telemetry_meta)`, `LLMProvider (LiteLLM / native async SDKs)`). | **Low** | **Queued for post-Gate-2 `sdd-replan` Mode D**: constitution files (`spec/architecture.md`, `spec/tech.md`, `spec/sdd-profile.md`) are intentionally unmodified during Gate 2 review and scheduled for Step 9 phase close. |
| **Lens 4: Test & Eval Quality (`#58`)** | Missing guardrail bypass tests (`\u200b`/`\u200c`/`\u200d`/`\u200f`/`\ufeff`, tatweel, dot-Luhn) and `SearchIntent` tatweel/Arabic-Indic slug tests. | **Medium** | **Fixed in `9b4ad0c`** (verified `#65`): added obfuscation bypass tests in `test_guardrails_and_intent.py` and Arabic-Indic/tatweel slug checks in `test_config_and_models.py`. |
| **Lens 4 (`#58`)** | Missing concurrent same-`session_id` upsert and `ttl_seconds <= 0` tests on `SQLAlchemySessionRepository`. | **Medium** | **Fixed in `9b4ad0c`** (verified `#65`): added `test_concurrent_same_session_upserts_and_ttl_cleanup` and `test_resilient_session_cooldown_recovery_and_data_error_isolation` in `test_session_stores.py`. |
| **Lens 4 (`#58`)** | Relaxed `/openapi.json` `T2.4` assertions omitted HTTP methods, `422`/`429`/`500`/`503` `ErrorResponse` `$ref` bindings, and DTO properties/enums. | **Medium** | **Fixed in `9b4ad0c`** (verified `#65`): tightened `test_openapi_schema_contract_for_frontend_codegen` in `test_fastapi_endpoints.py` and synced `feature-203/validation.md`. |
| **Lens 4 (`#58`)** | Intent extraction & rule-fallback unit test gaps (`fake.requests[1]` payload verification, `"من نون بس"`, `"بدون ميزانية"`, `"2,500"`, `"٤٫٥"`, `language_hint`, `llm_missing_search_query`, `llm_invalid_search_intent`). | **Medium** | **Fixed in `9b4ad0c`** (verified `#65`): added full assertions and branches in `test_guardrails_and_intent.py`. |
| **Lens 4 (`#58`)** | Missing all-waiter cancellation + distinct-key concurrency test (`test_cached_catalog.py`), `Bearer`/traceback/`422` `input`-omission & `GeminiLLMClient` `json_mode=False`/owned-`aclose()` & `workflow=` injection tests, and Windows TCP-timeout / `< 250 ms` disk-SQLite margin / `validation.md` warning alignment. | **Low** | **Fixed in `9b4ad0c`** (verified `#65`): added `test_cached_catalog_all_waiter_cancellation_and_distinct_key_concurrency`, error-scrubbing/Gemini/`workflow=` tests, short `2–3s` DB connect timeouts, CI-safe `< 300 ms` cached latency ceiling (`feature-202` `NFR3`/`T3.10`), and aligned `feature-203/validation.md:5`. |

---

## 4. Exact Validation Evidence (`#65` Independent Verifier Run on `9b4ad0c`)

All checks below were independently executed by `@verifier` (`#65`) against the final code and test state committed in `9b4ad0c` (100% offline unless marked opt-in `-m live`):

| Gate | Command | Observed Output | Status |
|:---|:---|:---|:---|
| **Full Offline Suite (`PI.2`, `INV-07`)** | `uv run --no-sync --directory backend pytest -v` | `collected 164 items / 1 deselected / 163 selected` → **`163 passed, 1 deselected, 1 warning in 17.22s`** (`0` failed, `0` skipped, `< 30 s`; `112` unit + `51` integration offline; deselected item is `@pytest.mark.live` `tests/integration/test_live_llm_smoke.py::test_live_llm_intent_extraction_smoke`; single warning is upstream `LangChainPendingDeprecationWarning` in `langgraph\cache\base\__init__.py:8`) | ✅ |
| **Phase 2 E2E (`PI.1`)** | `uv run --no-sync --directory backend pytest tests/integration/test_phase2_e2e.py -v` | **`13 passed, 1 warning in 6.94s`** (`0` failed, `0` skipped) | ✅ |
| **Feature 2.1 + Folded Phase 1 Subset** | `uv run --no-sync --directory backend pytest tests/unit/test_config_and_models.py tests/unit/test_llm_clients.py tests/unit/test_guardrails_and_intent.py tests/integration/test_cached_catalog.py tests/integration/test_phase1_e2e.py -v` | **`65 passed in 1.18s`** (`25` + `9` + `7` + `8` + `16`; `0` failed, `0` skipped) | ✅ |
| **Feature 2.2 Subset** | `uv run --no-sync --directory backend pytest tests/unit/test_session_stores.py tests/unit/test_agent_graph.py tests/integration/test_langgraph_session.py -v` | **`31 passed, 1 warning in 5.66s`** (`9` + `17` + `5`; `0` failed, `0` skipped) | ✅ |
| **Feature 2.3 Subset** | `uv run --no-sync --directory backend pytest tests/unit/test_api_middleware_and_schemas.py tests/integration/test_fastapi_endpoints.py -v` | **`16 passed, 1 warning in 6.94s`** (`7` + `9`; `0` failed, `0` skipped) | ✅ |
| **Phase 1 Unmodified Regression Files** | Included in `PI.2` (`test_ranking.py` `18`, `test_cache_stores.py` `6`, `test_catalog_seed.py` `5`, `test_catalog_serper.py` `9`) | **`38`** tests passing inside `163 passed` (`0` regressions) | ✅ |
| **Live Opt-In Guard (`-m live`)** | `uv run --no-sync --directory backend pytest tests/integration/test_live_llm_smoke.py -m live -v` | **`1 skipped in 0.20s`** (explicit opt-in; skips cleanly without live API keys) | ✅ |
| **Ruff Lint (`PI.3`)** | `uv run --no-sync --directory backend ruff check .` | **`All checks passed!`** (exit `0`) | ✅ |
| **Ruff Format (`PI.3`)** | `uv run --no-sync --directory backend ruff format --check .` | **`62 files already formatted`** (exit `0`) | ✅ |
| **Strict Mypy (`PI.3`)** | `uv run --no-sync --directory backend mypy src` | **`Success: no issues found in 43 source files`** (exit `0`) | ✅ |
| **Lockfile Integrity (`PI.3`)** | `uv lock --directory backend --check` | **`Resolved 70 packages in 2ms`** (exit `0`) | ✅ |
| **Tier 7 ASGI Smoke (`T7.1`)** | `uv run --no-sync --directory backend python -c "..."` (`commerce_ai.main:app` + `app.router.lifespan_context(app)` + `ASGITransport` over `/health`, `/api/v1/markets`, `/api/v1/search`, `/api/v1/chat`, `/openapi.json`) | **`T7.1 OK: ok 3 3 ok 3.1.0`** (all 5 endpoints `200 OK`, UUID4 `X-Request-ID`, clean shutdown) | ✅ |
| **Extra Gates (`PI.4`: `tests/evals`)** | `uv run --directory backend pytest tests/evals -v` | **Not Applicable** — `spec/sdd-profile.md` makes `backend/tests/evals/` mandatory from **Feature 4.1** onward once the golden Arabic/English benchmark suite is created | ⏭ N/A |
| **Tier 6 (Manual / Visual RTL UI)** | Manual live server smoke (presented at Gate 2) | **Not Applicable** for Phase 2 (`Next.js` RTL UI begins in Phase 3); optional manual live server verification commands provided below for human inspection | ⏭ N/A |

### Manual Live Server Smoke Commands (Optional Human Gate 2 Check)

```bash
# Terminal 1: Start FastAPI locally (offline seed/fake defaults; configure .env for live Serper/Gemini/Groq)
uv run --no-sync --directory backend uvicorn commerce_ai.main:app --reload --port 8000

# Terminal 2: Verify endpoints manually
curl -i http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/v1/markets
curl -s -X POST http://127.0.0.1:8000/api/v1/search -H "Content-Type: application/json" -d '{"query":"سماعة أنكر","country":"EG","store":"both","language":"ar"}'
curl -s -X POST http://127.0.0.1:8000/api/v1/chat -H "Content-Type: application/json" -d '{"message":"عايز سماعة بلوتوث أنكر تحت 2000 جنيه","country":"EG"}'

# Optional (only if live LLM API keys are set in env/.env):
uv run --no-sync --directory backend pytest tests/integration/test_live_llm_smoke.py -m live -v
```

---

## 5. Phase Gate 2 Recommendation & Post-Approval Actions

- **Verdict / Status**: **`APPROVED`** (Phase Gate 2 approved by human on 2026-11-15)
- **Recommendation**: Phase 2 (`phase/2-agent-and-api`) passes every offline test, static check, ASGI contract smoke, architectural invariant (`INV-01`–`INV-09`), and 4-lens deep review audit with **0 open High or Medium blockers**, and is ready for **🛑 Phase Gate 2** approval.
- **Post-Approval Actions (execute ONLY after human approval at Gate 2)**:
  1. Commit finalized Gate 2 review docs (`spec/phases/phase-2-agent-and-api/phase-review.md` and `spec/phases/phase-2-agent-and-api/phase-overview.md`).
  2. Run `sdd-changelog` to append Phase 2 stakeholder release notes (`Features 2.1`, `2.2`, `2.3`, plus folded Phase 1 follow-ups) to `CHANGELOG.md` and commit.
  3. Push branch to remote (`git push -u origin phase/2-agent-and-api`).
  4. Merge `phase/2-agent-and-api` into `main` using `git merge --no-ff` (per `spec/sdd-profile.md`) and update `phase-overview.md` Status to `Merged`.
  5. Run `sdd-replan` Mode D for Phase 2 closeout: record retrospective notes, confirm the verified backend commands in `spec/sdd-profile.md`, align Phase 0 wording in `spec/architecture.md` & `spec/tech.md` (`catalog_cache_key()`, `rank_top_offers`, `ChatResponse`, `LLMClient`), and verify Phase 3 readiness.
