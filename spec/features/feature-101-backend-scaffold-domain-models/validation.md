# Validation Criteria: Feature 1.1 — Backend Scaffold, Config & Regional Marketplace Domain Models

## 1. Success Definition
Feature 1.1 is complete when `uv sync --directory backend --all-extras --dev` installs all Phase 1 runtime and dev dependencies into the `commerce_ai` package cleanly, user-authored `backend/.env.example` and `frontend/.env.example` are preserved verbatim, root `.gitignore` appends Python cache patterns (`.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `*.egg-info/`), every requirement (`R1`–`R10`, `NFR1`–`NFR4`) is verified by passing offline unit tests in `backend/tests/unit/test_config_and_models.py`, and `uv run --directory backend pytest -v`, `ruff check .`, `ruff format --check .`, and `mypy src` all succeed with zero errors or external network access.

---

## 2. Requirement Traceability

| Requirement | Checks |
|:---|:---|
| R1 | T1.1, T5.1, T5.2, T5.3, T5.4 |
| R2 | T1.2, T3.1 |
| R3 | T1.3, T3.2 |
| R4 | T1.4, T3.3 |
| R5 | T1.5 |
| R6 | T1.6 |
| R7 | T1.7, T3.4, T3.5 |
| R8 | T1.8, T3.6, T3.7, T3.8 |
| R9 | T1.9, T3.9 |
| R10 | T1.10, T3.10 |
| NFR1 | T1.4, T3.3, T3.11 |
| NFR2 | T1.11, T5.4 |
| NFR3 | T4.1, T5.1 |
| NFR4 | T5.2, T5.3, T5.4 |

---

## 3. Verification Tiers

### Tier 1: Unit Verification
- [x] T1.1 — Package scaffold & Phase 1 imports (`commerce_ai`, `commerce_ai.config`, `commerce_ai.domain`, `commerce_ai.adapters`, `commerce_ai.adapters.catalog`, `commerce_ai.adapters.cache`) succeed and `pyproject.toml` declares all Phase 1 dependencies (`pydantic`, `pydantic-settings`, `httpx`, `redis`, `pytest`, `pytest-asyncio`, `fakeredis`, `ruff`, `mypy`), `asyncio_mode = "auto"`, and registered `live` marker (`tests/unit/test_config_and_models.py::test_package_scaffold_and_pyproject_contract`).
- [x] T1.2 — `ScoringConfig()` initializes defaults (`price_weight=0.55`, `rating_weight=0.45`, `bayesian_prior_count=25`, `bayesian_prior_mean=4.0`, `unrated_prior_rating=3.4`, `price_floor_ratio=0.15`, `price_ceiling_ratio=3.0`, `min_candidates_for_outlier_guard=3`, `top_k=3`) and accepts valid custom weights such as `0.70` / `0.30` (`tests/unit/test_config_and_models.py::test_scoring_config_defaults_and_overrides`).
- [x] T1.3 — `MARKET_REGISTRY` exposes `MarketConfig` entries with `currency` (`CurrencyCode.EGP`/`SAR`/`AED`) and `serper_gl` (`"eg"`/`"sa"`/`"ae"`), official Amazon hosts (`amazon.eg`, `amazon.sa`, `amazon.ae`), Noon path prefixes (`/egypt`, `/saudi`, `/uae`), and regional Google Shopping hosts (`tests/unit/test_config_and_models.py::test_market_registry_entries`).
- [x] T1.4 — `AppSettings()` uses expected defaults (`catalog_mode="auto"`, `cache_ttl_seconds=1800`, `serper_timeout_seconds=2.0`, `serper_api_key=None`, `redis_url=None`, nested `ScoringConfig`), loads `.env` copied from `backend/.env.example` using `extra="ignore"` (ignoring Phase 2/4 variables) while stripping inline `#` comments and surrounding whitespace on string env values (e.g., `CATALOG_MODE=auto                   # auto | seed | serper`), and masks `SecretStr` in `repr()`/`str()` (`tests/unit/test_config_and_models.py::test_app_settings_defaults_and_env_loading`).
- [x] T1.5 — Domain exceptions (`DomainError`, `OfferValidationError`, `CatalogProviderError`, `CacheStoreError`) preserve inheritance (`OfferValidationError` subclasses `DomainError` and `ValueError`) and `CatalogProviderError(provider="serper", retriable=True, reason="timeout")` constructs cleanly with no extra `message` argument and exposes `provider`, `retriable`, and `reason` (`tests/unit/test_config_and_models.py::test_domain_error_hierarchy`).
- [x] T1.6 — `StrEnum` enums expose exact uppercase member names and values: `CountryCode` (`EG="EG"`, `SA="SA"`, `AE="AE"`), `CurrencyCode` (`EGP="EGP"`, `SAR="SAR"`, `AED="AED"`), `StoreId` (`NOON="noon"`, `AMAZON="amazon"`), `StoreFilter` (`NOON="noon"`, `AMAZON="amazon"`, `BOTH="both"`), and `CatalogSourceMode` (`SEED="seed"`, `LIVE="live"`) (`tests/unit/test_config_and_models.py::test_domain_enums`).
- [x] T1.7 — `ProductOffer` accepts valid `EG`/`SA`/`AE` offers, quantizes `Decimal` `price` to `0.01` (e.g., `Decimal("1499.5")` -> `Decimal("1499.50")`), and validates `rating` (`0.0..5.0`) and `review_count` (`>= 0`) (`tests/unit/test_config_and_models.py::test_product_offer_valid_price_and_currency_pairing`).
- [x] T1.8 — `ProductOffer` and `commerce_ai.config.markets.validate_regional_offer_url(url, country=..., store=..., merchant_attribution=...)` accept valid HTTPS regional URLs (`amazon.eg`, `noon.com/egypt-en/...`, `amazon.sa`, `noon.com/saudi-ar/...`, `amazon.ae`, `noon.com/uae-en/...`) AND verified Google Shopping HTTPS links (`https://www.google.com/shopping/product/123`, `https://www.google.com.eg/shopping/product/123`) when merchant attribution identifies that regional Noon/Amazon store (`context={"merchant_attribution": "Amazon.eg"}` / `validate_regional_offer_url(..., country=CountryCode.EG, store=StoreId.NOON, merchant_attribution="Noon Egypt")`) (`tests/unit/test_config_and_models.py::test_product_offer_accepts_regional_and_attributed_google_urls`).
- [x] T1.9 — `SearchIntent.normalized_cache_key()` outputs canonical lowercase `"{country}:{store}:{slug}:{budget}:{min_rating}"` identically across equivalent whitespace/casing inputs for both Arabic (`"  سماعة   أنكر! "`) and English (`" Anker  Earbuds "`) queries with and without `max_budget`/`min_rating` (`tests/unit/test_config_and_models.py::test_search_intent_normalized_cache_key`).
- [x] T1.10 — `RankedOffer`, `RankingResult`, and `CatalogSearchResult` validate bounds (`rank` `1..3`, `value_score` `0..100`, `price_norm` `0..1`, `bayesian_rating` `0..5`) and survive JSON `model_dump_json()` / `model_validate_json()` round-trip (`tests/unit/test_config_and_models.py::test_ranking_and_catalog_result_models`).
- [x] T1.11 — AST/import check verifies `src/commerce_ai/config/` and `src/commerce_ai/domain/` contain zero imports from `httpx`, `redis`, `serper`, `langfuse`, or `boto3` (`tests/unit/test_config_and_models.py::test_hexagonal_boundary_no_vendor_imports`).

### Tier 2: Integration Verification
- **Status: Not Applicable**
- **Technical justification**: Feature 1.1 creates pure Python configuration, domain models, and exception definitions with zero HTTP clients, cache connections, database I/O, or FastAPI routes. Cross-adapter integration (`CachedCatalogProvider` + `SeedCatalogProvider` + `fakeredis` / `MockTransport`) is introduced in Feature 1.3 (`tests/integration/test_cached_catalog.py`), and HTTP API integration is introduced in Phase 2 (`Feature 2.3`).

### Tier 3: Error & Edge-Case Verification
- [x] T3.1 — Abnormal config: `ScoringConfig` rejects `price_weight + rating_weight != 1.0`, negative weights, `bayesian_prior_count <= 0`, `bayesian_prior_mean > 5.0` or `< 0.0`, `unrated_prior_rating > 5.0`, `price_floor_ratio <= 0.0` or `>= 1.0`, `price_ceiling_ratio <= 1.0`, and `top_k < 1` (`tests/unit/test_config_and_models.py::test_scoring_config_rejects_invalid_bounds`).
- [x] T3.2 — Boundary market lookup: `MARKET_REGISTRY` lookup for unknown keys raises `KeyError`, and merchant-attribution matching rejects foreign or third-party merchant names (`tests/unit/test_config_and_models.py::test_market_registry_rejects_unknown_market_and_foreign_merchants`).
- [x] T3.3 — Abnormal & secret-masking settings: `AppSettings` normalizes blank `SERPER_API_KEY=""` and `REDIS_URL=""` to `None`, rejects invalid `catalog_mode` or `<= 0` timeout/TTL, and never reveals `serper_api_key` or `redis://:secret@host` password in `repr()`/`str()` (`tests/unit/test_config_and_models.py::test_app_settings_secret_masking_and_invalid_values`).
- [x] T3.4 — Abnormal `ProductOffer` numeric values: rejects `price <= 0`, `Decimal("0.001")` quantizing to `0.00`, `NaN`/`Infinity`, negative `review_count`, and `rating` outside `[0.0, 5.0]` (`tests/unit/test_config_and_models.py::test_product_offer_rejects_invalid_price_and_rating`).
- [x] T3.5 — Market-currency mismatch: `ProductOffer` rejects mismatched `(country, currency)` combinations (`EG`+`SAR`, `SA`+`EGP`, `AE`+`EGP`) with `ValidationError` / `OfferValidationError` (`tests/unit/test_config_and_models.py::test_product_offer_rejects_currency_mismatch`).
- [x] T3.6 — Cross-country & cross-store URL rejection: `ProductOffer` rejects `amazon.com` or `amazon.sa` when `country="EG"`, `noon.com/saudi-en/item` when `country="EG"`, `noon.com/item` without regional path prefix, and `store="noon"` paired with an `amazon.eg` URL (`tests/unit/test_config_and_models.py::test_product_offer_rejects_cross_country_and_cross_store_urls`).
- [x] T3.7 — Non-HTTPS & unknown seller URL rejection: `ProductOffer` rejects `http://www.amazon.eg/dp/123`, non-HTTP schemes, non-HTTPS `image_url`, and third-party seller domains (`https://www.jumia.com.eg/...`, `https://www.ebay.com/...`) (`tests/unit/test_config_and_models.py::test_product_offer_rejects_insecure_and_third_party_urls`).
- [x] T3.8 — Google Shopping attribution edge cases: rejects Google Shopping links with missing attribution (in `validate_regional_offer_url` / attributed `model_validate`), unknown third-party attribution (`"Unknown Seller"`), cross-country attribution (`"Amazon.sa"` with `EG`), cross-country Google hosts (`google.com.sa` with `EG`), and non-shopping Google links (`google.com/search?q=...`), while allowing JSON cache round-trip deserialization (`CatalogSearchResult.model_validate_json`) (`tests/unit/test_config_and_models.py::test_google_shopping_url_attribution_validation_and_cache_roundtrip`).
- [x] T3.9 — `SearchIntent` boundary inputs: rejects blank `query`, `max_budget <= 0`, and `min_rating` outside `[0.0, 5.0]`, while handling Arabic/English punctuation & diacritics cleanly in `normalized_cache_key()` (`tests/unit/test_config_and_models.py::test_search_intent_validation_edge_cases`).
- [x] T3.10 — `RankedOffer` & `RankingResult` bounds: rejects `rank` outside `1..3`, `value_score` outside `0.0..100.0`, `price_norm` outside `0.0..1.0`, `bayesian_rating` outside `0.0..5.0`, and negative counts (`tests/unit/test_config_and_models.py::test_ranked_offer_rejects_out_of_bounds`).
- [x] T3.11 — Repository hygiene & PII exclusion: inspects `backend/.env.example` and root `.gitignore` to confirm zero hardcoded keys/passwords, `.env` ignored, and Python cache patterns present, and verifies `ProductOffer`/`SearchIntent` schemas define zero payment or sensitive PII fields (`tests/unit/test_config_and_models.py::test_env_example_and_pii_exclusion`).

### Tier 4: Regression Checks
- [x] T4.1 — Full backend suite runs cleanly offline in `< 30 s` with zero skipped or relaxed assertions: `uv run --directory backend pytest -v` (`INV-07`).

### Tier 5: Build, Lint & Type Checks
- [x] T5.1 — Dependency & environment sync succeeds: `uv sync --directory backend --all-extras --dev`.
- [x] T5.2 — Ruff lint passes with zero issues: `uv run --directory backend ruff check .`.
- [x] T5.3 — Ruff format check passes with zero diffs: `uv run --directory backend ruff format --check .`.
- [x] T5.4 — Strict mypy check passes with zero errors: `uv run --directory backend mypy src`.

### Tier 6: Manual / Visual Verification
- **Status: Not Applicable**
- **Technical justification**: Feature 1.1 delivers headless backend Python scaffolding, configuration, and domain models with no user interface, browser rendering, or interactive visual layout. Manual/visual `RTL` UI verification begins in Phase 3 (`Feature 3.1`).

### Tier 7: API / CLI / Application Checks
- **Status: Not Applicable**
- **Technical justification**: Feature 1.1 does not expose any HTTP endpoints, FastAPI `uvicorn` application entrypoint, or user-facing CLI commands. Runtime API endpoint checks begin in Phase 2 (`Feature 2.3`).

### Extra Gates
- **Status: Not Applicable**
- **Technical justification**: Per `spec/sdd-profile.md`, the `uv run --directory backend pytest tests/evals -v` evaluation gate becomes mandatory from Feature 4.1 onward once the `LangGraph` agent and end-to-end recommendation pipeline exist; Feature 1.1 introduces only package scaffolding, config, and schemas.

---

## 4. Automated Execution Commands

```text
uv sync --directory backend --all-extras --dev
uv run --directory backend pytest tests/unit/test_config_and_models.py -v
uv run --directory backend pytest -v
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy src
```

---

## 5. Execution Results (filled in execute mode)

| Check | Result (✅ / ❌ / ⏭ N/A) | Evidence (command output summary, counts) |
|:---|:---|:---|
| `T1.1`–`T1.11` (Unit) | ✅ | `uv run --directory backend pytest tests/unit/test_config_and_models.py -v` — 11/11 Tier 1 checks passed (within `22 passed in 0.86s`, 0 skipped, 0 warnings) |
| `Tier 2` (Integration) | ⏭ N/A | Pure Python config, domain schemas, and errors only; integration suite introduced in Feature 1.3 (`tests/integration/test_cached_catalog.py`) |
| `T3.1`–`T3.11` (Error & Edge) | ✅ | `uv run --directory backend pytest tests/unit/test_config_and_models.py -v` — 11/11 Tier 3 checks passed (within `22 passed in 0.86s`, 0 skipped, 0 warnings) |
| `T4.1` (Regression) | ✅ | `uv run --directory backend pytest -v` — `22 passed in 0.40s` offline with `-m "not live"` and 0 skipped assertions |
| `T5.1` (Env Sync) | ✅ | `uv sync --directory backend --all-extras --dev` — resolved 30 packages (`commerce-ai==0.1.0` editable, `backend/uv.lock` generated) |
| `T5.2` (Ruff Lint) | ✅ | `uv run --directory backend ruff check .` — `All checks passed!` (0 errors) |
| `T5.3` (Ruff Format) | ✅ | `uv run --directory backend ruff format --check .` — `15 files already formatted` (0 diffs) |
| `T5.4` (Mypy Strict) | ✅ | `uv run --directory backend mypy src` — `Success: no issues found in 11 source files` |
| `Tier 6` (Manual / Visual) | ⏭ N/A | Headless backend Python package only; RTL UI verification begins in Phase 3 (`Feature 3.1`) |
| `Tier 7` (API / CLI) | ⏭ N/A | No FastAPI routes or CLI entrypoint in Feature 1.1; endpoint checks begin in Phase 2 (`Feature 2.3`) |
| `Extra Gates` (Evals) | ⏭ N/A | `tests/evals/` becomes mandatory from Feature 4.1 onward per `spec/sdd-profile.md` |
