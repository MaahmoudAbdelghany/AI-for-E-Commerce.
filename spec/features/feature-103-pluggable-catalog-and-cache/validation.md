# Validation Criteria: Feature 1.3 — Pluggable Catalog Layer & TTL Caching

## 1. Success Definition

Feature 1.3 is complete when `domain/ports.py` exposes pure `CatalogProvider` and `CacheStore` protocols with zero vendor imports, both `InMemoryTTLCache` and `fakeredis`-verified `RedisCacheStore` pass all TTL/error/fallback tests offline, versioned bilingual `EG`/`SA`/`AE` seed datasets (`5+` categories across `Noon` and `Amazon` including all deliberate ranking traps) load and match Arabic/English queries cleanly, `SerperShoppingProvider` passes `httpx.MockTransport` tests proving strictly 1 `POST /shopping` call (`num=40`, `2.0s` timeout, `P2` regional store validation, zero secret leakage, typed `CatalogProviderError` with zero silent seed fallback), `CachedCatalogProvider` + factory integration tests pass offline, and the full backend `pytest`, `ruff`, and `mypy` suite passes cleanly.

## 2. Requirement Traceability

| Requirement | Checks |
|:---|:---|
| R1 | T1.1, T5.3 |
| R2 | T1.2, T3.7 |
| R3 | T1.3, T3.6 |
| R4 | T1.4, T2.3, T3.8 |
| R5 | T1.5, T1.6 |
| R6 | T1.5, T1.6, T3.9 |
| R7 | T1.7, T1.8, T2.2 |
| R8 | T1.8, T1.9, T3.4 |
| R9 | T3.1, T3.2, T3.3 |
| R10 | T2.1, T2.2 |
| R11 | T3.5 |
| R12 | T1.10, T2.3, T3.10 |
| NFR1 | T1.7, T2.2 |
| NFR2 | T1.9, T3.3, T3.6 |
| NFR3 | T1.1, T5.3 |
| NFR4 | T1.3, T1.7, T2.2, T4.1 |
| NFR5 | T1.7, T5.1 |
| NFR6 | T4.1, T5.1, T5.2, T5.3, T5.4 |

---

## 3. Verification Tiers

### Tier 1: Unit Verification

- [x] **T1.1 — Pure Hexagonal Ports (`INV-02`)**: Inspect/import `commerce_ai.domain.ports` and assert `CatalogProvider` and `CacheStore` expose the exact async method signatures (`search_offers`, `get`, `set`, `delete`) with zero imports from `adapters`, `httpx`, or `redis` (`backend/tests/unit/test_catalog_seed.py::test_ports_have_no_vendor_imports`).
- [x] **T1.2 — `InMemoryTTLCache` Basic & TTL Expiry**: Store serialized strings with a positive TTL using a deterministic monotonic clock stub → `get(key)` returns value before expiry, returns `None` after TTL elapses, and `delete(key)` removes existing entries (`backend/tests/unit/test_cache_stores.py::test_in_memory_cache_ttl_lifecycle`).
- [x] **T1.3 — `RedisCacheStore` Offline via `fakeredis` (`P1`, `INV-07`)**: Instantiate `RedisCacheStore` with `fakeredis.aioredis.FakeRedis` → `set` with `ttl_seconds`, `get`, TTL expiration, and `delete` behave identically to Redis 7 completely offline with zero Docker or external Redis (`backend/tests/unit/test_cache_stores.py::test_redis_cache_store_with_fakeredis`).
- [x] **T1.4 — Cache Factory Unset `REDIS_URL` Default (`P1`)**: Invoke cache factory with `AppSettings(redis_url=None)` → returns an `InMemoryTTLCache` instance ready for immediate local/offline use (`backend/tests/unit/test_cache_stores.py::test_cache_factory_defaults_to_memory_when_redis_url_unset`).
- [x] **T1.5 — Seed Catalog Coverage, Categories & Traps (`P6`)**: Load `eg.json`, `sa.json`, and `ae.json` via `SeedCatalogProvider` → verify each country contains `>= 5` distinct categories across both `StoreId.NOON` and `StoreId.AMAZON`, every item passes `ProductOffer` & `P2` regional currency/URL validation, and every country includes accessory traps, `5.0`-star/`1`-review traps, unrated (`rating=None`, `review_count=0`) offers, and `>= 4x` scalper outliers (`backend/tests/unit/test_catalog_seed.py::test_seed_datasets_cover_markets_categories_and_traps`).
- [x] **T1.6 — `SeedCatalogProvider` Bilingual Search & Store Filtering (`P6`)**: Query `SeedCatalogProvider` with Arabic (e.g., `"سماعة بلوتوث أنكر"`) and English (e.g., `"Anker earbuds"`) intents across `StoreFilter.BOTH`, `StoreFilter.NOON`, and `StoreFilter.AMAZON` → returns `CatalogSearchResult` with `source_mode=CatalogSourceMode.SEED`, `cache_hit=False`, strict store/country scoping, and preserved trap candidates matching query keywords (`backend/tests/unit/test_catalog_seed.py::test_seed_provider_bilingual_query_and_store_filter`).
- [x] **T1.7 — Single-Call `SerperShoppingProvider` Request Contract (`P5`, `NFR1`, `INV-06`)**: Execute `search_offers(intent)` against `httpx.MockTransport` for `EG`/`SA`/`AE`, `ar`/`en`, and `noon`/`amazon`/`both` → asserts `call_count == 1`, method `POST`, URL `https://google.serper.dev/shopping`, timeout configured to `2.0s` (`AppSettings.serper_timeout_seconds`), JSON payload `num == 40`, `gl` in `{"eg","sa","ae"}`, `hl` in `{"ar","en"}`, store hint included when `intent.store != both`, and `X-API-KEY` header passed (`backend/tests/unit/test_catalog_serper.py::test_serper_sends_single_configured_shopping_request`).
- [x] **T1.8 — Serper Regional Parsing & Google Shopping Attribution (`P2`, `P5`)**: Feed `httpx.MockTransport` a realistic `"shopping"` response containing official regional URLs (`amazon.eg`, `noon.com/egypt-ar/...`), Google Shopping HTTPS URLs (`google.com/shopping/...`, `google.com.eg/...`) with `"Amazon.eg"` / `"Noon"` attribution, and formatted prices → `SerperShoppingProvider` delegates `P2` verification via `validate_regional_offer_url(..., merchant_attribution=...)` / `ProductOffer.model_validate(..., context={"merchant_attribution": ...})` and returns valid `ProductOffer` entries with `CatalogSourceMode.LIVE` and quantized `Decimal` prices in `EGP`/`SAR`/`AED` (`backend/tests/unit/test_catalog_serper.py::test_serper_parses_official_and_attributed_google_shopping_offers`).
- [x] **T1.9 — Serper Rejection of Cross-Country & Non-Regional Sellers (`P2`, `INV-05`, `INV-09`)**: Include `amazon.com` (`US`), non-HTTPS `http://`, an unattributed Google Shopping link (`source=""`), and third-party merchants (e.g., `"RandomShop"`, Google Shopping link attributed to `"B.TECH"` or `"Amazon.com"`) alongside valid regional Noon/Amazon offers → unauthorized/unattributed offers fail `P2` validation and are strictly excluded while valid offers are preserved (`backend/tests/unit/test_catalog_serper.py::test_serper_filters_out_cross_country_and_third_party_offers`).
- [x] **T1.10 — Catalog Factory `CatalogMode` Selection (`P6`)**: Test catalog factory under `catalog_mode="seed"`, `catalog_mode="auto"` with empty `serper_api_key`, `catalog_mode="auto"` with configured `serper_api_key`, and `catalog_mode="serper"` with configured key → resolves `SeedCatalogProvider` vs `SerperShoppingProvider` deterministically (`backend/tests/unit/test_catalog_serper.py::test_catalog_factory_mode_resolution`).

### Tier 2: Integration Verification

- [x] **T2.1 — `CachedCatalogProvider` + `InMemoryTTLCache` + `SeedCatalogProvider` Flow**: Execute first `search_offers(intent)` → spy confirms 1 inner provider call, result has `cache_hit=False`, `source_mode=CatalogSourceMode.SEED`, and `InMemoryTTLCache` stores JSON under `intent.normalized_cache_key()`; execute second identical `search_offers(intent)` → inner provider call count stays `1` and result returns `cache_hit=True` with identical offers (`backend/tests/integration/test_cached_catalog.py::test_cached_seed_catalog_miss_then_hit`).
- [x] **T2.2 — `CachedCatalogProvider` + `RedisCacheStore` (`fakeredis`) + `SerperShoppingProvider` (`MockTransport`) End-to-End (`P1`, `P5`, `INV-07`)**: Execute miss then repeat query using `fakeredis` and `httpx.MockTransport` → miss sends **1** mocked HTTP request (`source_mode=CatalogSourceMode.LIVE`, `cache_hit=False`) and populates `fakeredis`; repeat query returns `cache_hit=True`, `source_mode=CatalogSourceMode.LIVE`, and **0** additional HTTP requests (`backend/tests/integration/test_cached_catalog.py::test_cached_live_serper_with_fakeredis`).
- [x] **T2.3 — End-to-End Factory Wiring with Unreachable Redis Fallback (`P1`, `P6`)**: Wire cache factory + catalog factory using `AppSettings(redis_url="redis://127.0.0.1:6399/0", catalog_mode="auto", serper_api_key=None)` with unreachable Redis → system falls back cleanly to `InMemoryTTLCache` + `SeedCatalogProvider` and completes cached search end-to-end (`backend/tests/integration/test_cached_catalog.py::test_factories_wire_fallback_cache_and_seed_provider`).

### Tier 3: Error & Edge-Case Verification

- [x] **T3.1 — Serper Timeout Raises `CatalogProviderError` Without Seed Fallback (`P5`, `P6`, `INV-08`)**: Simulate `httpx.ReadTimeout` at `2.0s` in `MockTransport` → `SerperShoppingProvider` raises `CatalogProviderError(provider="serper", retriable=True, ...)` and never serves seed items (`backend/tests/unit/test_catalog_serper.py::test_serper_timeout_raises_retriable_error_without_seed_fallback`).
- [x] **T3.2 — Serper HTTP Status & Malformed JSON Handling (`INV-08`)**: Simulate HTTP `401`, `429`, `500`, invalid JSON body, and non-list `"shopping"` payload → raises `CatalogProviderError` with accurate `retriable` flag (`False` for `401`/malformed, `True` for `429`/`500`) (`backend/tests/unit/test_catalog_serper.py::test_serper_http_and_schema_errors_raise_typed_error`).
- [x] **T3.3 — Secret Redaction Across Serper Errors & Logs (`INV-01`)**: Trigger `SerperShoppingProvider` failure with a distinct test `SecretStr("serper-secret-test-999")` and capture exception text + `caplog` → secret string never appears anywhere in error `reason`, `str(exc)`, or logs (`backend/tests/unit/test_catalog_serper.py::test_serper_never_logs_or_leaks_api_key`).
- [x] **T3.4 — Malformed Item Skipping & Honest Empty Result (`INV-05`)**: Feed Serper `200 OK` with invalid price string (`"N/A"`), missing URL, and empty `"shopping": []` → invalid entries are skipped cleanly without hallucinated defaults, and zero qualifying items returns `CatalogSearchResult(offers=[], source_mode=CatalogSourceMode.LIVE, cache_hit=False)` (`backend/tests/unit/test_catalog_serper.py::test_serper_skips_malformed_items_and_handles_empty_results`).
- [x] **T3.5 — `CachedCatalogProvider` Resilience & Never-Cache-Failures (`INV-08`)**: (a) Inner provider raises `CatalogProviderError` → error propagates and cache remains empty; (b) `CacheStore.get()` raises `CacheStoreError` or holds corrupt non-JSON string → provider still executes and returns valid `CatalogSearchResult`; (c) `CacheStore.set()` raises `CacheStoreError` → valid `CatalogSearchResult` is still returned with `cache_hit=False` (`backend/tests/integration/test_cached_catalog.py::test_cached_catalog_error_resilience_and_no_error_caching`).
- [x] **T3.6 — `RedisCacheStore` Wraps Errors & Redacts `REDIS_URL` Credentials (`INV-01`, `INV-08`)**: Simulate `RedisError` on `get`/`set` when configured with `redis://user:supersecret@localhost:6379/0` → raises `CacheStoreError` without exposing `"supersecret"` in exception text or logs (`backend/tests/unit/test_cache_stores.py::test_redis_cache_error_wrapping_and_secret_redaction`).
- [x] **T3.7 — `InMemoryTTLCache` Boundary Conditions**: Verify `delete()` on an absent key is a safe no-op and `set(..., ttl_seconds=0)` does not retain stale data (`backend/tests/unit/test_cache_stores.py::test_in_memory_cache_edge_cases`).
- [x] **T3.8 — Cache Factory Fallback on Unreachable `REDIS_URL` (`P1`, `INV-08`)**: Pass an unreachable `REDIS_URL` (`redis://:secretpass@127.0.0.1:6399/0`) to the cache factory → falls back to `InMemoryTTLCache` with sanitized warning (no `"secretpass"` leaked) (`backend/tests/unit/test_cache_stores.py::test_cache_factory_falls_back_when_redis_unreachable`).
- [x] **T3.9 — `SeedCatalogProvider` Non-Matching Query & Arabic Variants**: Query a nonexistent product token (e.g., `"xyz-nonexistent-999"`) and Arabic hamza/teh-marbuta variations (e.g., `"ايفون 15"` / `"سماعه بلوتوث"`) → nonexistent query returns empty `offers=[]` (`source_mode=SEED`) and Arabic normalization matches expected seed items (`backend/tests/unit/test_catalog_seed.py::test_seed_provider_arabic_variants_and_empty_match`).
- [x] **T3.10 — Explicit `catalog_mode="serper"` Without `SERPER_API_KEY` (`P6`)**: Invoke catalog factory with `catalog_mode="serper"` and `serper_api_key=None` (or empty string) → raises `CatalogProviderError(provider="serper", retriable=False, ...)` instead of silently returning `SeedCatalogProvider` (`backend/tests/unit/test_catalog_serper.py::test_catalog_factory_serper_mode_requires_api_key`).

### Tier 4: Regression Checks

- [x] **T4.1 — Full Offline Backend Test Suite (`INV-07`)**: Run `uv run --directory backend pytest -v` (confirming all Feature 1.1, Feature 1.2, and Feature 1.3 unit and integration tests pass 100% offline in `< 30 s`, with any optional `@pytest.mark.live` check excluded from offline CI runs).

### Tier 5: Build, Lint & Type Checks

- [x] **T5.1 — Ruff Lint Check**: `uv run --directory backend ruff check .` passes with zero errors.
- [x] **T5.2 — Ruff Format Check**: `uv run --directory backend ruff format --check .` passes with zero formatting diffs.
- [x] **T5.3 — Strict Type Check**: `uv run --directory backend mypy src` passes with zero type errors across `domain/ports.py`, `adapters/cache/`, and `adapters/catalog/`.
- [x] **T5.4 — Environment & Dependency Sync**: `uv sync --directory backend --all-extras --dev` resolves and syncs cleanly using Feature 1.1's `pyproject.toml` without adding or altering dependencies.

### Tier 6: Manual / Visual Verification

`Status: Not Applicable` — **Technical Justification**: Feature 1.3 implements backend hexagonal protocols, cache stores, JSON seed fixtures, an async HTTP adapter, and factories only; there are no frontend UI components, RTL layouts, rendered templates, or interactive browser screens (the Next.js web interface is introduced in Phase 3).

### Tier 7: API / CLI / Application Checks

`Status: Not Applicable` — **Technical Justification**: Feature 1.3 exposes no FastAPI HTTP routes, ASGI application server, or CLI entrypoint (`main.py` and `/api/v1/*` routers belong to Feature 2.3); all adapter contracts and factory wiring are exercised directly via async unit tests and integration tests (`test_cached_catalog.py`).

### Extra Gates (from `spec/sdd-profile.md`)

`Status: Not Applicable` — **Technical Justification**: Per `spec/sdd-profile.md`, the `uv run --directory backend pytest tests/evals -v` evaluation gate becomes mandatory from Feature 4.1 onward once the bounded `LangGraph` workflow and golden dataset exist; Phase 1 validates seed traps and adapter behavior through deterministic unit and integration checks.

---

## 4. Automated Execution Commands

```text
uv sync --directory backend --all-extras --dev
uv run --directory backend pytest tests/unit/test_cache_stores.py tests/unit/test_catalog_seed.py tests/unit/test_catalog_serper.py tests/integration/test_cached_catalog.py -v
uv run --directory backend pytest -v
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy src
```

## 5. Execution Results (filled in execute mode)

| Check | Result (✅ / ❌ / ⏭ N/A) | Evidence (command output summary, counts) |
|:---|:---|:---|
| **T1.1–T1.10** (Unit checks) | ✅ | `uv run --no-sync --directory backend pytest tests/unit/test_cache_stores.py tests/unit/test_catalog_seed.py tests/unit/test_catalog_serper.py tests/integration/test_cached_catalog.py -v` → `23 passed in 1.13s` (covers all Tier 1 unit checks offline) |
| **T2.1–T2.3** (Integration checks) | ✅ | Included in `23 passed in 1.13s` (`tests/integration/test_cached_catalog.py`: `test_cached_seed_catalog_miss_then_hit`, `test_cached_live_serper_with_fakeredis`, `test_factories_wire_fallback_cache_and_seed_provider`) |
| **T3.1–T3.10** (Error & Edge checks) | ✅ | Included in `23 passed in 1.13s` across `test_cache_stores.py`, `test_catalog_seed.py`, `test_catalog_serper.py`, and `test_cached_catalog.py` |
| **T4.1** (Full-suite regression) | ✅ | `uv run --no-sync --directory backend pytest -v` → `63 passed in 1.21s` (`22` Feature 1.1 + `18` Feature 1.2 + `23` Feature 1.3 tests 100% offline, verified after Feature 1.2 commit `9c4ddf6`) |
| **T5.1** (Ruff lint) | ✅ | `uv run --no-sync --directory backend ruff check .` → `All checks passed!` |
| **T5.2** (Ruff format) | ✅ | `uv run --no-sync --directory backend ruff format --check .` → `29 files already formatted` |
| **T5.3** (Mypy strict) | ✅ | `uv run --no-sync --directory backend mypy src` → `Success: no issues found in 20 source files` |
| **T5.4** (Env sync / lock) | ✅ | `uv lock --directory backend --check` → `Resolved 30 packages in 1ms` (`backend/pyproject.toml` and `backend/uv.lock` untouched per `P7`) |
| **Tier 6 / Tier 7 / Extra** | ⏭ N/A | Technical justifications in §3 (no UI/routes in Feature 1.3; `tests/evals` starts in Feature 4.1) |
