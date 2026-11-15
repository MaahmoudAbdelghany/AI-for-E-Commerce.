# Validation Criteria: Feature 1.2 — Deterministic Top-3 Value Scoring Engine & Anti-Accessory/Outlier Filter

## 1. Success Definition

Feature 1.2 is completely proven successful when `backend/src/commerce_ai/domain/ranking.py` and `backend/tests/unit/test_ranking.py` pass 100% offline under `uv run --directory backend pytest`, demonstrating accurate two-stage Arabic/English anti-accessory and median-price outlier filtering (`P4`), Bayesian 1-review trap resistance (`INV-03`), conservative `unrated_prior_rating = 3.4` handling and single-item `P_norm = 1.0` normalization (`P3`), deterministic tie-breaking and `match_reasons` assignment, graceful `0–2` partial degradation (`INV-05`, `INV-08`), zero vendor SDK imports (`INV-02`), and clean `ruff` and `mypy` verification (`spec/sdd-profile.md`) without modifying `backend/pyproject.toml` or `backend/src/commerce_ai/domain/__init__.py` (`P7`).

---

## 2. Requirement Traceability

| Requirement | Checks |
|:---|:---|
| R1 | T1.1, T1.9, T3.1 |
| R2 | T1.4, T1.5 |
| R3 | T1.6, T1.7, T3.5 |
| R4 | T1.8, T3.4, T3.5 |
| R5 | T1.2, T1.3, T1.4 |
| R6 | T1.1, T3.3 |
| R7 | T1.1, T1.9 |
| R8 | T1.1, T3.6 |
| R9 | T1.10 |
| R10 | T1.10, T3.1, T3.2 |
| NFR1 | T1.1, T3.7, T4.1 |
| NFR2 | T1.11, T5.1, T5.3 |
| NFR3 | T3.7, T4.1 |
| NFR4 | T5.1, T5.2, T5.3 |

---

## 3. Verification Tiers

### Tier 1: Unit Verification
- [x] T1.1 — **Balanced Top-3 Value Ranking & Determinism**: 5 valid `EG` offers across `noon` and `amazon` with varied prices and `review_count >= 50` using default `ScoringConfig` (`price_weight=0.55`, `rating_weight=0.45`) → returns `total_candidates=5`, `len(ranked_offers)==3`, sequential ranks `1..3`, exact `price_norm`, `bayesian_rating`, rounded `value_score`, `degraded_fewer_than_k=False`, and bit-identical output across repeated calls (`tests/unit/test_ranking.py::test_balanced_top_3_ranking_and_determinism`)
- [x] T1.2 — **Bayesian 1-Review 5-Star Trap**: Equal/comparable-price offers comparing `5.0` rating with `1` review vs `4.8` rating with `600` reviews (`m=25`, `C=4.0`) → `5.0/1` shrinks to `≈ 4.0385` while `4.8/600` scores `≈ 4.7680`, so the `4.8/600` product strictly outranks the `5.0/1` listing (`tests/unit/test_ranking.py::test_bayesian_one_review_five_star_trap`)
- [x] T1.3 — **Unrated & Zero-Review Conservative Prior (`P3`)**: Offers with `rating=None` or `review_count=0` when `intent.min_rating is None` → remain eligible, receive `bayesian_rating == 3.4` (`config.unrated_prior_rating`, below `bayesian_prior_mean=4.0`), and rank below comparable-price well-reviewed offers (`tests/unit/test_ranking.py::test_unrated_and_zero_review_prior`)
- [x] T1.4 — **Hard Eligibility Filters & `min_rating` Unrated Exclusion (`P3`)**: Mixed pool containing `in_stock=False`, wrong `country`, wrong `store`, `price > max_budget`, rated offer below `min_rating`, AND `rating=None` / `review_count=0` when `min_rating=4.0` → all ineligible offers (including unrated/zero-review offers under `min_rating`) are excluded prior to Stage 1/2 counts (`tests/unit/test_ranking.py::test_hard_filters_and_min_rating_excludes_unrated`)
- [x] T1.5 — **`StoreFilter.BOTH` & Bilingual `exclude_keywords`**: Intent with `store=StoreFilter.BOTH` and `exclude_keywords=("refurbished", "مجدد")` → retains eligible offers from both `noon` and `amazon` while filtering matching refurbished titles across case and Arabic orthographic variants (`tests/unit/test_ranking.py::test_store_both_and_bilingual_exclude_keywords`)
- [x] T1.6 — **Stage 1 Bilingual Anti-Accessory Filter Rejection (`P4`)**: Primary product search (`"iPhone 15"` and `"سماعة بلوتوث أنكر"`) against pool containing English (`case`, `cover`, `protector`, `cable`, `cord`, `charger`, `adapter`, `strap`, `holder`, `mount`, `skin`, `sleeve`) and Arabic (`جراب`, `كفر`, `حافظة`, `شاحن`, `اسكرينة`, `حماية شاشة` including `"واقي وحماية الشاشة"`, `وصلة`, `كابل`, `سلك`, `حامل`, `سوار`, plus tashkeel/alef-maksura variants) accessory titles plus non-accessory titles (`"Showcase Edition"`, `"Record Player"`) → rejects true accessories, sets `filtered_accessories_count`, and preserves primary non-accessory items (`tests/unit/test_ranking.py::test_stage1_bilingual_accessory_rejection`)
- [x] T1.7 — **Stage 1 Intent-Aware Positive Accessory Search & Opt-In (`P4`)**: Positive bilingual searches (`"iPhone 15 case"`, `"Anker earbuds case"`, `"جراب آيفون 15"`, `"جراب أنكر"`) retain matching same-concept bilingual offers (such as `"جراب ... - ... Case"`) while still rejecting unrelated accessories (e.g., `"charger"` / `"شاحن"`), and `intent.include_accessories=True` bypasses Stage 1 completely with `filtered_accessories_count == 0` (`tests/unit/test_ranking.py::test_stage1_positive_accessory_search_and_opt_in`)
- [x] T1.8 — **Stage 2 Median Price Floor, Upper Anomaly & `max_budget` Interaction (`P4`)**: Pool of `>= 3` post-Stage-1 candidates with median `1000.00`: rejects floor outlier `< 150.00` (`< 0.15 * median`) and upper scalper anomaly `> 3000.00` (`> 3.0 * median`) when `intent.max_budget is None` (`filtered_outliers_count == 2`); when `intent.max_budget=Decimal("4000.00")`, a `3500.00` listing (`> 3.0 * median` and `<= max_budget`) is accommodated and preserved (`tests/unit/test_ranking.py::test_stage2_median_price_floor_ceiling_and_budget`)
- [x] T1.9 — **Configurable `ScoringConfig` Weights & Parameters Override (`INV-03`)**: Passing custom `ScoringConfig(price_weight=0.20, rating_weight=0.80, bayesian_prior_count=10, unrated_prior_rating=3.0, top_k=2)` shifts the winning rank toward higher rating and caps output to `2` items without editing code (`tests/unit/test_ranking.py::test_configurable_scoring_weights_override`)
- [x] T1.10 — **Deterministic `match_reasons` & Zero Field Mutation (`INV-05`)**: Verifies each `RankedOffer` carries non-empty deterministic `match_reasons` tags (`"best_overall_value"`, `"lowest_price"`, `"top_bayesian_rating"`, `"high_review_confidence"`, `"within_budget"`, `"unrated_fallback"`) matching actual candidate attributes, and verifies returned `RankedOffer.offer` objects match input `ProductOffer` fields unchanged (`tests/unit/test_ranking.py::test_match_reasons_and_offer_immutability`)
- [x] T1.11 — **Hexagonal Boundary / Zero Vendor SDK Imports (`INV-02`)**: Inspects AST imports of `commerce_ai/domain/ranking.py` → confirms zero imports of `commerce_ai.adapters`, `httpx`, `redis`, `serper`, `langfuse`, `boto3`, `openai`, `litellm`, `langgraph`, `fastapi`, or `sqlalchemy` (`tests/unit/test_ranking.py::test_zero_vendor_imports_hexagonal_boundary`)

### Tier 2: Integration Verification
`Status: Not Applicable` — `commerce_ai.domain.ranking` is an isolated, side-effect-free pure domain module that operates exclusively in memory on `ProductOffer`, `SearchIntent`, and `ScoringConfig` values with no database, cache, HTTP, or `CatalogProvider` I/O (`INV-02`). End-to-end integration across `SeedCatalogProvider -> CachedCatalogProvider -> rank_top_offers` is covered in Feature 1.3 (`backend/tests/integration/test_cached_catalog.py`) and Phase 1 integration validation (`PI.1` in `spec/phases/phase-1-core-foundation/phase-overview.md`).

### Tier 3: Error & Edge-Case Verification
- [x] T3.1 — **Abnormal / Empty Input & Total Filter Elimination (`INV-08`)**: Calling `rank_top_offers([], intent)` and calling with offers all eliminated by filters → returns `RankingResult(ranked_offers=[], filtered_accessories_count=..., filtered_outliers_count=..., degraded_fewer_than_k=True)` cleanly with zero exceptions (`tests/unit/test_ranking.py::test_empty_and_all_filtered_graceful_degradation`)
- [x] T3.2 — **Boundary / Partial Matches (`0–2` Offers, `INV-05`, `INV-08`)**: Pool yielding `1` or `2` qualifying offers when `config.top_k=3` → returns exactly `1` or `2` `RankedOffer` entries, `degraded_fewer_than_k=True`, and zero fabricated padding (`tests/unit/test_ranking.py::test_partial_matches_degraded_flag_no_padding`)
- [x] T3.3 — **Boundary / Single Candidate & Equal Prices (`P_max == P_min`, `P3`)**: Single surviving candidate (`len == 1`) and multi-candidate equal-price pool (`P_max == P_min`) → computes `price_norm == 1.0` and finite `value_score` in `[0.0, 100.0]` with no division-by-zero error (`tests/unit/test_ranking.py::test_single_candidate_and_equal_price_norm`)
- [x] T3.4 — **Boundary / Stage 2 Guard Inactive Below `min_candidates_for_outlier_guard`**: Exactly `2` surviving post-Stage-1 candidates (`< 3`) priced at `100.00` and `1000.00` → Stage 2 does not filter either candidate and sets `filtered_outliers_count == 0` (`tests/unit/test_ranking.py::test_stage2_inactive_below_min_candidates`)
- [x] T3.5 — **Boundary / Two-Stage Filter Ordering (`Stage 1` Before `Stage 2`, `P4`)**: Pool containing `3` smartphones (`~20000`) and `4` cheap accessories (`~150`) where accessories would otherwise lower the median to `150` and cause Stage 2 to reject the smartphones → Stage 1 removes the `4` accessories first (`filtered_accessories_count == 4`), leaving the `3` smartphones with median `20000` (`filtered_outliers_count == 0`) (`tests/unit/test_ranking.py::test_stage1_runs_before_stage2_median`)
- [x] T3.6 — **Boundary / Exact Value-Score Tie-Breaking Cascade**: Offers tied at identical `value_score` break ties deterministically by higher `review_count`, then lower `price`, then lexicographical `offer_id` (`tests/unit/test_ranking.py::test_tie_breaking_review_count_price_offer_id`)
- [x] T3.7 — **Offline Determinism & Latency Budget (`INV-07`, `NFR1`)**: Ranking `100` mixed offers runs 100% offline with zero env vars or sockets in `< 2 ms` typical (`< 50 ms` CI wall-clock assertion ceiling to avoid tracing flakiness) (`tests/unit/test_ranking.py::test_offline_determinism_and_performance_budget`)

### Tier 4: Regression Checks
- [x] T4.1 — Full backend suite passes 100% offline (`INV-07`): `uv run --directory backend pytest -v` *(confirmed independently by `verifier` / `coordinator`: `80 passed`)*

### Tier 5: Build, Lint & Type Checks
- [x] T5.1 — Lint clean: `uv run --directory backend ruff check .` *(scoped Feature 1.2 check + full-repo `ruff check .` confirmed clean)*
- [x] T5.2 — Format check clean: `uv run --directory backend ruff format --check .` *(scoped Feature 1.2 check + full-repo `30 files already formatted` confirmed clean)*
- [x] T5.3 — Strict type check clean: `uv run --directory backend mypy src` *(scoped Feature 1.2 check + full-repo `20 source files` confirmed clean)*
- Build check: `Status: Not Applicable` — Python backend uses `uv` package sync with no separate compilation or bundle build step configured in `spec/sdd-profile.md`; package integrity and types are validated by `T5.3` (`mypy src`) and `T4.1` (`pytest`).

### Tier 6: Manual / Visual Verification
`Status: Not Applicable` — Feature 1.2 delivers a headless Python domain function (`rank_top_offers`) with no web UI, RTL layout, or interactive CLI surface; visual Arabic/English Top-3 comparison card verification begins in Phase 3 (Features 3.1–3.2).

### Tier 7: API / CLI / Application Checks
`Status: Not Applicable` — Feature 1.2 exposes an internal Python domain module only; HTTP endpoints (`/api/v1/search`, `/api/v1/chat`) and live FastAPI server entrypoints are introduced in Phase 2 (Feature 2.3).

### Extra Gates
`Status: Not Applicable` — Per `spec/sdd-profile.md`, the `tests/evals` extra gate becomes mandatory from Feature 4.1 onward once the bounded LangGraph workflow exists; Phase 1 validates bilingual accessory and Bayesian traps deterministically via Tier 1 and Tier 3 unit tests (`T1.2`–`T1.8`, `T3.5`).

---

## 4. Automated Execution Commands

```text
uv sync --directory backend --all-extras --dev
uv run --directory backend pytest tests/unit/test_ranking.py -v
uv run --directory backend pytest -v
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy src
```

---

## 5. Execution Results (filled in execute mode)

| Check | Result (✅ / ❌ / ⏭ N/A) | Evidence (command output summary, counts) |
|:---|:---|:---|
| T1.1–T1.11 | ✅ | `uv run --no-sync --directory backend pytest tests/unit/test_ranking.py -v` → `18 passed in 0.39s` (all 11 Tier 1 checks `test_balanced_top_3_ranking_and_determinism` through `test_zero_vendor_imports_hexagonal_boundary` passed offline) |
| Tier 2 | ⏭ N/A | Isolated pure domain module (`INV-02`); integration verified in Feature 1.3 and Phase 1 `PI.1` |
| T3.1–T3.7 | ✅ | `uv run --no-sync --directory backend pytest tests/unit/test_ranking.py -v` → all 7 Tier 3 checks (`test_empty_and_all_filtered_graceful_degradation` through `test_offline_determinism_and_performance_budget`) passed inside the `18 passed in 0.39s` run |
| T4.1 | ✅ | `uv run --no-sync --directory backend pytest -v` → `80 passed in 1.51s` offline across all Feature 1.1, Feature 1.2, Feature 1.3, and Phase 1 E2E tests |
| T5.1 | ✅ | `uv run --no-sync --directory backend ruff check .` → `All checks passed!` |
| T5.2 | ✅ | `uv run --no-sync --directory backend ruff format --check .` → `30 files already formatted` |
| T5.3 | ✅ | `uv run --no-sync --directory backend mypy src` → `Success: no issues found in 20 source files` |
| Tier 6 / Tier 7 / Extra Gates | ⏭ N/A | Headless Python domain engine with no UI/HTTP surface or LLM eval gate in Phase 1 |
