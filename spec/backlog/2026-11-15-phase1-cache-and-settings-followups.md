# Backlog: Phase 1 Cache, Settings & Single-Flight Follow-Ups

- **Date**: 2026-11-15
- **Raised during**: Phase 1 (`phase/1-core-foundation`)
- **Status**: Open
- **Type**: Tech debt

## Question / Idea
Should we tighten three non-blocking Phase 1 design constraints—locked by Feature 1.1 contracts (`R4`, `R9`) or deferred ahead of concurrent FastAPI traffic—before Phase 2 introduces multi-turn `LangGraph` orchestration and concurrent HTTP endpoints? Specifically:
1. Redacting `AppSettings.redis_url` passwords inside Pydantic serialization (`model_dump()` / `model_dump_json()`), not only `repr()`/`str()`/`safe_summary()` (Security Lens `#49`).
2. Adding Arabic orthographic folding (`أ/إ/آ/ٱ -> ا`, `ة -> ه`, `ى -> ي`) and separating upstream catalog cache keys (`{country}:{store}:{language}:{slug}`) from downstream ranking filters (`max_budget`, `min_rating`) in `SearchIntent.normalized_cache_key()` (Architecture Lens `#51`).
3. Adding per-key single-flight request coalescing to `CachedCatalogProvider.search_offers()` to prevent concurrent cold-cache stampedes on `$0.001` `SerperShoppingProvider` calls ahead of Feature 2.3 FastAPI endpoints (Architecture Lens `#51`).

## Context
- **Relevant files & specs**:
  - `backend/src/commerce_ai/config/settings.py` (`AppSettings.redis_url`, `__repr_args__`, `safe_summary()`, `redact_url_password`)
  - `backend/src/commerce_ai/adapters/cache/factory.py` (`create_cache_store`) and `backend/src/commerce_ai/adapters/cache/redis_store.py` (`RedisCacheStore`, `extract_secret_password`)
  - `backend/src/commerce_ai/domain/models.py` (`SearchIntent.normalized_cache_key()`)
  - `backend/src/commerce_ai/domain/ranking.py` (`_ARABIC_CHAR_TRANS`) and `backend/src/commerce_ai/adapters/catalog/seed_provider.py` (`normalize_bilingual_text`)
  - `backend/src/commerce_ai/adapters/catalog/cached_provider.py` (`CachedCatalogProvider.search_offers`)
  - `backend/src/commerce_ai/adapters/catalog/serper_provider.py` (`SerperShoppingProvider.search_offers`, `hl=intent.language`)
  - `spec/features/feature-101-backend-scaffold-domain-models/requirements.md` (`R4`, `R9`) and `plan.md` (`D6`)
- **Constraints & Invariants (`spec/tech.md`)**:
  - `INV-01`: Zero hardcoded or leaked credentials in logs, diagnostics, or serialized config outputs.
  - `INV-04`: Bounded agent/search cost ceiling (`~$0.001 <= $0.002` per uncached query via TTL caching and minimized duplicate Serper calls).
  - `INV-08`: Graceful degradation (`CachedCatalogProvider` must never cache `CatalogProviderError` failures).
  - Phase 1 Feature 1.1 `R4` locks `AppSettings.redis_url: str | None = None`, and `R9` / `D6` lock the 5-part `"{country}:{store}:{slug}:{budget}:{min_rating}"` key format tested in `backend/tests/unit/test_config_and_models.py`.

## Findings
1. **`AppSettings.redis_url` serialization exposure (`#49`, Low)**: `serper_api_key` uses `SecretStr | None`, whereas `redis_url` is typed `str | None`. `AppSettings.__repr_args__()` and `safe_summary()` mask passwords via `redact_url_password()`, but Pydantic's inherited `model_dump()` and `model_dump_json()` return the unredacted `REDIS_URL` string in plaintext if settings are ever serialized for debugging or telemetry.
2. **`SearchIntent.normalized_cache_key()` Arabic folding & key scope (`#51`, Low)**: `SearchIntent.normalized_cache_key()` applies `NFKC`, `.lower()`, and `_ARABIC_DIACRITICS_RE` stripping, but omits Arabic letter folding (`أ/إ/آ/ٱ -> ا`, `ة -> ه`, `ى -> ي`) that `domain/ranking.py` and `seed_provider.py` apply. Consequently, equivalent queries like `"سماعة أنكر"` and `"سماعه انكر"` produce distinct keys (`eg:both:سماعة-أنكر:none:none` vs `eg:both:سماعه-انكر:none:none`), triggering duplicate `$0.001` Serper calls. Furthermore, `normalized_cache_key()` omits `intent.language` (used as `hl` in `SerperShoppingProvider`, risking `"ar"`/`"en"` cache collisions) while including `max_budget` and `min_rating` even though upstream `CatalogProvider`s do not filter by them—fragmenting cache keys whenever downstream ranking filters change.
3. **`CachedCatalogProvider` cold-cache stampede risk (`#51`, Low)**: `CachedCatalogProvider.search_offers()` checks `self._cache.get(cache_key)` and awaits `self._provider.search_offers(intent)` without per-key concurrency coordination. Under concurrent FastAPI requests (Feature 2.3) hitting the same normalized key on a cold cache or right after TTL expiry, multiple coroutines miss `get()` simultaneously and issue redundant paid `SerperShoppingProvider` HTTP calls.

## Recommendations
| # | Recommendation | Human decision (accepted / changed / rejected) |
|:---|:---|:---|
| 1 | Migrate `AppSettings.redis_url` from `str | None` to `SecretStr | None` (unwrapping in `create_cache_store` / `RedisCacheStore`) or add a redacting Pydantic `@field_serializer` on `redis_url` so `model_dump()` and `model_dump_json()` mask Redis passwords consistently with `repr()`/`str()`/`safe_summary()` (update Feature 1.1 `R4`). | |
| 2 | Update `SearchIntent.normalized_cache_key()` (or add a dedicated upstream catalog cache key method) to apply Arabic orthographic folding (`أ/إ/آ/ٱ -> ا`, `ة -> ه`, `ى -> ي`) and separate `{country}:{store}:{language}:{slug}` for upstream catalog caching from downstream `max_budget`/`min_rating` ranking filters (update Feature 1.1 `R9` / `D6`). | |
| 3 | Add per-key single-flight request coalescing (`asyncio.Lock` + in-flight future/task registry keyed by `cache_key`) inside `CachedCatalogProvider.search_offers()` so concurrent cold-cache/expired misses share a single upstream provider call while propagating `CatalogProviderError` cleanly without caching errors. | |

## Next Step
Schedule via `sdd-replan` (Mode B) into **Phase 2** (`Feature 2.3 — FastAPI Service` or a small pre-2.3 `S` hardening slice): estimated size **`S`** (~1 day total across config serialization, cache key migration, and `CachedCatalogProvider` single-flight coalescing + concurrency tests).
