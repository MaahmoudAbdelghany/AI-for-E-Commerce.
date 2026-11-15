# Validation Criteria: Feature 2.2 — Bounded LangGraph Shopping Agent Workflow & Async Session Memory

## 1. Success Definition

Feature 2.2 is proven completely successful when `InMemorySessionStore`, `SQLAlchemySessionRepository`, `ResilientSessionRepository` (`create_session_repository`), grounded `prompts.py`, zero-token bilingual `templates.py`, and the compiled `LangGraph` `ShoppingAssistantWorkflow` pass 100% offline under `uv run --directory backend pytest`, proving bounded `<= 2` LLM calls per turn (`INV-04`), pre-DB/pre-LLM guardrail short-circuiting (`INV-09`), multi-turn refinements reusing `CachedCatalogProvider` with zero duplicate catalog calls and `< 250 ms` cached latency (`P4`), zero-catalog `COMPARE` execution, smart adaptive `explain` modes (`INV-05`), automatic DB-to-memory/LLM-to-template/catalog-to-degraded resilience (`INV-08`), redacted DB credentials (`INV-01`), strict hexagonal AST boundaries (`INV-02`), and clean `ruff` / `mypy` / `uv lock --check` checks without touching Feature 2.1, Feature 2.3, or Sensitive Area files (`P7`).

---

## 2. Requirement Traceability

| Requirement | Checks |
|:---|:---|
| R1 | T1.1, T3.1 |
| R2 | T1.2, T2.1, T3.2 |
| R3 | T1.3, T3.3 |
| R4 | T1.4 |
| R5 | T1.5 |
| R6 | T1.6, T2.1 |
| R7 | T1.7, T2.3 |
| R8 | T1.8, T2.1, T2.2 |
| R9 | T1.9, T2.2, T3.8 |
| R10 | T1.10, T3.9 |
| R11 | T1.10, T1.11, T2.1, T3.4 |
| R12 | T3.4, T3.5, T3.7 |
| R13 | T1.12, T3.6, T3.8 |
| NFR1 | T3.3, T3.6 |
| NFR2 | T1.13, T5.1, T5.3 |
| NFR3 | T2.2, T3.10 |
| NFR4 | T2.1, T2.4, T3.10, T4.1 |
| NFR5 | T4.1, T5.1, T5.2, T5.3, T5.4 |

---

## 3. Verification Tiers

### Tier 1: Unit Verification

- [x] **T1.1 — `InMemorySessionStore` Bounded LRU, Monotonic TTL & Turn Trimming (`R1`)**: Store sessions using a stubbed monotonic clock with `max_sessions=2`, `max_turns=3` → confirms `get_session()` refreshes LRU recency and returns defensive copies, inserting a 3rd active session evicts the least-recently-used key, advancing clock past `ttl_seconds` expires the entry, saving `> 3` turns keeps only the latest `3` turns, and `delete_session()` removes entries cleanly (`backend/tests/unit/test_session_stores.py::test_in_memory_session_store_lru_ttl_and_trimming`).
- [x] **T1.2 — `SQLAlchemySessionRepository` CRUD, `commerce_sessions` Auto-Create & Google Shopping Round-Trip (`R2`)**: Initialize `SQLAlchemySessionRepository` against `sqlite+aiosqlite` (in-memory and temp file), save a `SessionState` containing `last_ranked_offers` with an attributed `https://www.google.com/shopping/product/...` URL and `> max_turns` turns → `initialize()` creates `commerce_sessions` via `Base.metadata.create_all` without Alembic scripts, `get_session()` restores the exact `SessionState` including the verified Google Shopping offer URL and trimmed turns, `delete_session()` removes it, and `close()` disposes cleanly (`backend/tests/unit/test_session_stores.py::test_sqlalchemy_session_repository_crud_and_google_url_roundtrip`).
- [x] **T1.3 — `create_session_repository` Dialect Resolution (`R3`)**: Call `create_session_repository(AppSettings(database_url="sqlite+aiosqlite:///..."))` and `create_session_repository(AppSettings(database_url="postgresql+asyncpg://user:pass@localhost:5432/commerce_ai"))` (sync inspection without live Postgres connection) → returns `ResilientSessionRepository` with `backend_name="sqlite"`, `is_degraded=False` for SQLite and `backend_name="postgresql"`, `is_degraded=False` for PostgreSQL (while degraded fallback to `backend_name="memory"`, `is_degraded=True` is verified in `T3.3`) (`backend/tests/unit/test_session_stores.py::test_session_factory_resolves_sqlite_and_postgres_dialects`).
- [x] **T1.4 — Grounded Call #2 Prompt Builder & Token Cap (`R4`, `INV-04`, `INV-05`)**: Call `build_explanation_request(...)` for `SEARCH` (`ar`/`en`), `COMPARE`, and `degraded_fewer_than_k=True` → verifies `LLMRequest.max_tokens <= 300`, embeds exact verified `RankedOffer` fields (`offer_id`, `title`, `price`, `currency`, `store`, `rating`, `review_count`, `value_score`, `bayesian_rating`, `match_reasons`, `url`), isolates offer titles inside untrusted data delimiters, and includes anti-hallucination & partial-count instructions (`backend/tests/unit/test_agent_graph.py::test_prompts_grounding_and_token_budget`).
- [x] **T1.5 — Zero-Token Bilingual Deterministic Templates (`R5`, `INV-05`, `INV-08`, `INV-09`)**: Render every template helper in both `"ar"` and `"en"` (Top-3 summary, 0-offer empty notice, `1–2` partial `< top_k` honest notice, saved-offers `COMPARE` side-by-side comparison, `CLARIFY` standard + empty-saved-compare, `OFF_TOPIC`, `REFUSED`, and `DEGRADED`) → confirms matching language output, exact verified prices/stores/URLs with zero fabricated offers, honest partial/empty wording, and zero echoed secrets/PII in `REFUSED` (`backend/tests/unit/test_agent_graph.py::test_bilingual_templates_cover_all_outcomes`).
- [x] **T1.6 — Compiled `LangGraph` Topology & `SEARCH` Flow (`R6`)**: Inspect compiled `ShoppingAssistantWorkflow` graph nodes and run a valid Arabic/English search turn → verifies all required nodes (`guard`, `load_session`, `parse`, `route`, `respond_guard_or_clarify`, `fetch_catalog`, `rank_offers`, `compare_saved`, `explain`, `save_session`) exist and `run_turn()` returns `ChatTurnResult(status=TurnStatus.OK, action=TurnAction.SEARCH, top_offers=...)` (`backend/tests/unit/test_agent_graph.py::test_workflow_graph_topology_and_search_flow`).
- [x] **T1.7 — Pre-DB / Pre-LLM Guardrail Short-Circuit (`R7`, `INV-09`)**: Submit prompt-injection and credit-card/PII messages to `ShoppingAssistantWorkflow.run_turn(...)` backed by spy `LLMClient`, `CatalogProvider`, and `SessionRepository` → returns `ChatTurnResult(status=TurnStatus.REFUSED, action=TurnAction.REFUSE, top_offers=[], ...)` with `llm_client` call count `0`, `catalog_provider` call count `0`, and `session_repository` `get_session`/`save_session` call counts both `0` (`backend/tests/unit/test_agent_graph.py::test_guard_short_circuit_skips_llm_catalog_and_db`).
- [x] **T1.8 — Multi-Turn Session Loading & Last-6 Turn Window (`R8`, `P4`)**: Pre-seed a `SessionState` containing `last_intent`, `last_ranked_offers`, and `10` turns, then run a follow-up refinement turn with a spy on `extract_turn_intent` → confirms `load_session` supplies `prior_intent=state.last_intent`, `recent_turns` capped to last `6` turns, and `has_saved_offers=True` (`backend/tests/unit/test_agent_graph.py::test_parse_passes_prior_intent_and_last_six_turns`).
- [x] **T1.9 — `COMPARE` Answers From Saved Offers With 0 Catalog Calls (`R9`, `P4`)**: Seed a session with saved `last_ranked_offers` and run `"قارن بين الأول والثاني"` (`TurnAction.COMPARE`) → routes through `compare_saved`, returns saved `top_offers`, and invokes `CatalogProvider` `0` times (`telemetry.catalog_called is False`) (`backend/tests/unit/test_agent_graph.py::test_compare_uses_saved_offers_with_zero_catalog_calls`).
- [x] **T1.10 — Smart Adaptive `explain` Modes & `llm_calls <= 2` (`R10`, `R11`, `INV-04`, `P4`)**: Exercise `explain_mode="auto"` across (a) cache miss (`llm_calls=2`, `used_template_summary=False`), (b) cache hit (`llm_calls=1`, `used_template_summary=True`, Call #2 skipped), (c) `COMPARE` (`llm_calls=2`, `used_template_summary=False`), (d) `explain_mode="template"` (`llm_calls=1`, `used_template_summary=True`), and (e) `llm_client=None` (`llm_calls=0`, `used_template_summary=True`) → confirms exact token/call bounds `<= 2` (`backend/tests/unit/test_agent_graph.py::test_smart_adaptive_explain_modes_and_call_ceiling`).
- [x] **T1.11 — Strict Unmodified `top_offers` Grounding (`R11`, `INV-05`)**: Configure `FakeLLMClient` Call #2 to return prose mentioning an invented price/URL → `ChatTurnResult.top_offers` retains exact unmodified `RankedOffer` objects from `rank_top_offers` / `last_ranked_offers` (`backend/tests/unit/test_agent_graph.py::test_top_offers_strictly_grounded_unmodified_from_ranker`).
- [x] **T1.12 — `save_session` State Updates & `session_max_turns` Trimming (`R13`)**: Run `12` sequential turns with `session_max_turns=10` followed by `CLARIFY`/`OFF_TOPIC` turns → persisted `SessionState.turns` never exceeds `10` entries, while `last_intent` and `last_ranked_offers` update on `SEARCH` and remain intact on non-search turns (`backend/tests/unit/test_agent_graph.py::test_save_session_updates_and_trims_turn_window`).
- [x] **T1.13 — AST Hexagonal Boundary Verification (`NFR2`, `INV-02`)**: Parse AST of `agent/prompts.py`, `agent/templates.py`, and `agent/graph.py` → asserts zero imports from `commerce_ai.adapters`, `httpx`, `redis`, `sqlalchemy`, `aiosqlite`, `asyncpg`, `serper`, `langfuse`, `boto3`, `openai`, `litellm`, `google`, or `groq` (`backend/tests/unit/test_agent_graph.py::test_agent_modules_hexagonal_boundary_no_vendor_imports`).

### Tier 2: Integration Verification

- [x] **T2.1 — Multi-Turn SQLite + CachedCatalog + FakeLLM Search Flow (`R2`, `R6`, `R8`, `R11`, `NFR4`)**: Wire `ShoppingAssistantWorkflow` with `SeedCatalogProvider`, `CachedCatalogProvider(InMemoryTTLCache)`, `SQLAlchemySessionRepository` (`sqlite+aiosqlite` temp file), and `FakeLLMClient` → Turn 1 Arabic search (*"عايز سماعة بلوتوث أنكر"*) hits `SeedCatalogProvider` once (`cache_hit=False`, `llm_calls=2`, `used_template_summary=False`), persists `SessionState` in SQLite, and returns Top-3 verified offers (`backend/tests/integration/test_langgraph_session.py::test_multiturn_search_refine_compare_and_guardrail_sqlite`).
- [x] **T2.2 — Multi-Turn Budget Refinement Cache Reuse, Country Switch & `COMPARE` (`R8`, `R9`, `NFR3`)**: Continuing from `T2.1`, Turn 2 (*"أرخص تحت ٢٠٠٠"*) merges `max_budget=2000` onto `last_intent`, hits `CachedCatalogProvider` (`catalog_cache_hit=True`, **0** additional `SeedCatalogProvider` calls), re-ranks strictly `<= 2000`, and skips Call #2 (`used_template_summary=True`, `llm_calls=1`); Turn 3 (*"بدّل للسعودية"*) switches `country=CountryCode.SA` (`SAR` offers) and Turn 4 (*"قارن بين الأول والثاني"*) compares saved offers with **0** `CatalogProvider` calls (`backend/tests/integration/test_langgraph_session.py::test_multiturn_search_refine_compare_and_guardrail_sqlite`, `test_multiturn_country_switch_and_compare_flow`).
- [x] **T2.3 — Multi-Turn Guardrail Refusal Leaves Persisted SQLite Session Clean (`R7`, `INV-09`)**: Submit a payment-card or prompt-injection payload against an active persisted SQLite `session_id` → returns `TurnStatus.REFUSED`, and inspecting `SQLAlchemySessionRepository.get_session(session_id)` confirms prior turns, `last_intent`, and `last_ranked_offers` are 100% untouched (`backend/tests/integration/test_langgraph_session.py::test_guardrail_refusal_leaves_prior_sqlite_session_intact`).
- [x] **T2.4 — Offline No-LLM End-to-End Multi-Turn Workflow (`NFR4`, `INV-07`, `INV-08`)**: Instantiate `ShoppingAssistantWorkflow` with `llm_client=None`, `SeedCatalogProvider`, and `SQLAlchemySessionRepository` (`sqlite+aiosqlite`) → runs search -> budget refinement -> compare end-to-end with `llm_calls == 0`, `used_rule_intent_fallback == True`, and `used_template_summary == True` (`backend/tests/integration/test_langgraph_session.py::test_offline_no_llm_multiturn_workflow`).

### Tier 3: Error & Edge-Case Verification

- [x] **T3.1 — `InMemorySessionStore` Invalid Bounds, Zero TTL, Missing Delete & Expired-First Eviction (`R1`)**: Verify `max_sessions <= 0` or `max_turns < 2` raises `ValueError`, `save_session(..., ttl_seconds=0)` deletes/skips storage, `delete_session("missing")` is a safe no-op, and capacity insertion prunes expired entries before evicting active LRU items (`backend/tests/unit/test_session_stores.py::test_in_memory_session_store_edge_cases`).
- [x] **T3.2 — `SQLAlchemySessionRepository` Expired Session Cleanup & Corrupt JSON (`R2`)**: Advance injected `wall_clock` past `expires_at_epoch` → `get_session()` deletes the expired row and returns `None`; corrupt `payload_json` stored in `commerce_sessions` raises `SessionStoreError` cleanly (`backend/tests/unit/test_session_stores.py::test_sqlalchemy_session_expiry_and_corrupt_payload`).
- [x] **T3.3 — DB Credential Redaction (`NFR1`, `INV-01`) & Automatic Fallback (`R3`, `INV-08`)**: Test `SQLAlchemySessionRepository` and `create_session_repository` with `postgresql+asyncpg://admin:supersecretpw99@127.0.0.1:5999/commerce_ai` and unreachable/failing SQLite engine/runtime I/O → `"supersecretpw99"` never appears in `SessionStoreError` or logs (`caplog`), and `ResilientSessionRepository` degrades transparently to `InMemorySessionStore` (`backend_name="memory"`, `is_degraded=True`) across `initialize()` and runtime calls (`backend/tests/unit/test_session_stores.py::test_sqlalchemy_error_redacts_credentials`, `test_session_factory_fallback_on_init_and_runtime_errors`).
- [x] **T3.4 — `LLMProviderError` in `explain` Falls Back to `templates.py` (`R11`, `R12`, `INV-08`)**: Configure Call #2 `FakeLLMClient` to raise `LLMProviderError("gemini", retriable=True, reason="timeout")` (and separately return empty whitespace) → workflow catches cleanly, returns `status=TurnStatus.OK`, preserves `top_offers`, and sets `used_template_summary=True` (`backend/tests/unit/test_agent_graph.py::test_explain_llm_error_falls_back_to_template`).
- [x] **T3.5 — `CatalogProviderError` Returns `TurnStatus.DEGRADED` (`R12`, `INV-08`)**: Configure `CatalogProvider` to raise `CatalogProviderError("serper", retriable=True, reason="timeout")` → workflow returns `ChatTurnResult(status=TurnStatus.DEGRADED, top_offers=[], ranking_result=None, ...)` with localized outage message, `used_template_summary=True`, sanitized `telemetry.degraded_reason`, and prior `last_ranked_offers` preserved (`backend/tests/unit/test_agent_graph.py::test_catalog_provider_error_returns_degraded_status`).
- [x] **T3.6 — `SessionStoreError` on Load/Save Degrades Without Failing Response (`R13`, `NFR1`, `INV-08`)**: Inject failing `SessionRepository` raising `SessionStoreError` on `get_session()` and `save_session()` → `run_turn()` still returns valid `ChatTurnResult` without raising or leaking secrets (`backend/tests/unit/test_agent_graph.py::test_session_store_error_degrades_gracefully`).
- [x] **T3.7 — Honest `0` & `1–2` Partial Offers Degradation (`R12`, `INV-05`, `INV-08`)**: Catalog returning `0` offers or `1–2` offers (`degraded_fewer_than_k=True`) → returns exact `0–2` offers with zero synthetic padding and honest Arabic/English template notice (`backend/tests/unit/test_agent_graph.py::test_zero_and_partial_offers_honest_degradation`).
- [x] **T3.8 — Empty-Saved `COMPARE`, `CLARIFY`, `OFF_TOPIC` & Defensive `intent=None` Routing (`R9`, `R13`)**: Run `COMPARE` on an empty session (`last_ranked_offers=[]`), `CLARIFY`, `OFF_TOPIC`, and mocked `SEARCH` with `intent=None` → zero `CatalogProvider` calls, `TurnStatus.CLARIFY` / `TurnStatus.OFF_TOPIC`, and intact prior `last_intent`/`last_ranked_offers` (`backend/tests/unit/test_agent_graph.py::test_compare_empty_offers_and_clarify_off_topic_routing`).
- [x] **T3.9 — Hard `llm_calls <= 2` Ceiling in `"llm"` `explain_mode` (`R10`, `INV-04`)**: Execute uncached search with `explain_mode="llm"` and `FakeLLMClient` → executes at most `2` calls total (`1` parse + `1` explain) and never retries beyond `2` (`backend/tests/unit/test_agent_graph.py::test_explain_mode_llm_respects_two_call_ceiling`).
- [x] **T3.10 — Cached Turn Latency & Offline Determinism Budget (`NFR3`, `NFR4`, `INV-07`)**: Benchmark cached repeat/refinement `run_turn()` in `"auto"` mode offline → completes in `< 250 ms` wall-clock (`<= 300 ms` P95 target) with `0` Call #2 tokens and `0` upstream catalog calls (`backend/tests/integration/test_langgraph_session.py::test_cached_turn_latency_budget_and_determinism`).

### Tier 4: Regression Checks

- [x] **T4.1 — Full Offline Backend Test Suite (`NFR4`, `NFR5`, `INV-07`)**: `uv run --directory backend pytest -v` passes 100% offline with zero failures, skips, or relaxed assertions.

### Tier 5: Build, Lint & Type Checks

- [x] **T5.1 — Ruff Lint (`NFR2`, `NFR5`)**: `uv run --directory backend ruff check .` passes with zero errors.
- [x] **T5.2 — Ruff Format (`NFR5`)**: `uv run --directory backend ruff format --check .` passes with zero formatting diffs.
- [x] **T5.3 — Strict Type Check (`NFR2`, `NFR5`)**: `uv run --directory backend mypy src` passes with zero type errors.
- [x] **T5.4 — Lockfile & Partition Verification (`NFR5`, `P7`)**: `uv lock --directory backend --check` passes cleanly without modifying `pyproject.toml` or `uv.lock`.
- Build check: `Status: Not Applicable` — *Technical justification*: Python backend uses `uv` package sync with no separate compilation or bundle build step configured in `spec/sdd-profile.md`; package integrity and static types are validated by `T5.3` (`mypy src`) and `T4.1` (`pytest`).

### Tier 6: Manual / Visual Verification

`Status: Not Applicable` — *Technical justification*: Feature 2.2 delivers headless Python `SessionRepository` adapters, prompt/template modules, and the internal `LangGraph` workflow only; there is no web UI, RTL layout, or browser interface (the Next.js Arabic-first RTL frontend begins in Phase 3).

### Tier 7: API / CLI / Application Checks

`Status: Not Applicable` — *Technical justification*: Feature 2.2 exposes internal workflow (`ShoppingAssistantWorkflow.run_turn`) and persistence contracts only; versioned HTTP endpoints (`/api/v1/chat`, `/api/v1/search`, `/api/v1/markets`, `/health`) and `commerce_ai.main:create_app` are delivered and checked at Tier 7 in Feature 2.3.

### Extra Gates (from `spec/sdd-profile.md`)

`Status: Not Applicable` — *Technical justification*: Per `spec/sdd-profile.md`, the `uv run --directory backend pytest tests/evals -v` golden evaluation gate becomes mandatory from **Feature 4.1** onward; Feature 2.2 verifies workflow routing, grounding, session persistence, and degradation deterministically via `T1.1`–`T4.1`.

---

## 4. Automated Execution Commands

```text
uv run --directory backend pytest tests/unit/test_session_stores.py tests/unit/test_agent_graph.py tests/integration/test_langgraph_session.py -v
uv run --directory backend pytest -v
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy src
uv lock --directory backend --check
```

---

## 5. Execution Results (filled in execute mode)

| Check | Result (✅ / ❌ / ⏭ N/A) | Evidence (command output summary, counts) |
|:---|:---|:---|
| T1.1–T1.13 | ✅ Passed | `uv run --no-sync --directory backend pytest tests/unit/test_session_stores.py tests/unit/test_agent_graph.py tests/integration/test_langgraph_session.py -v` -> all 23 unit tests passed (`7` in `test_session_stores.py`, `16` in `test_agent_graph.py`; combined run `28 passed, 1 warning in 6.05s`) |
| T2.1–T2.4 | ✅ Passed | Covered in the same Feature 2.2 pytest run -> all `5` tests in `tests/integration/test_langgraph_session.py` passed (`28 passed, 1 warning in 6.05s`) |
| T3.1–T3.10 | ✅ Passed | All 10 edge/error tests (`T3.1–T3.3` in `test_session_stores.py`, `T3.4–T3.9` in `test_agent_graph.py`, `T3.10` in `test_langgraph_session.py`) passed (`28 passed, 1 warning in 6.05s`) |
| T4.1 | ✅ Passed | `uv run --no-sync --directory backend pytest -v` -> `130 passed, 1 deselected, 1 warning in 7.16s` (`not live` marker deselected per `pyproject.toml`; 0 failures, 0 skips) |
| T5.1–T5.4 | ✅ Passed | `ruff check .` -> `All checks passed!`; `ruff format --check .` -> `53 files already formatted`; `mypy src` -> `Success: no issues found in 37 source files`; `uv lock --directory backend --check` -> `Resolved 70 packages in 2ms` |
| Tier 6 / Tier 7 / Extra Gates | ⏭ N/A | Technical justifications recorded in §3 |
