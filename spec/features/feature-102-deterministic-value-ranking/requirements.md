# Requirements: Feature 1.2 — Deterministic Top-3 Value Scoring Engine & Anti-Accessory/Outlier Filter

> Decisions and behaviours, not implementation micro-details. Every requirement must be testable and map to at least one check in `validation.md`.

## 1. Functional Requirements

| ID | Requirement | Validated by (validation.md check) |
|:---|:---|:---|
| R1 | The system must expose `rank_top_offers(offers: Sequence[ProductOffer], intent: SearchIntent, config: ScoringConfig \| None = None) -> RankingResult` in `commerce_ai.domain.ranking`, defaulting to `ScoringConfig()` when `config` is `None` and recording `total_candidates = len(offers)` in `RankingResult`. | T1.1, T1.9, T3.1 |
| R2 | Before Stage 1 and Stage 2 filtering, the engine must apply hard eligibility filters rejecting any offer where `in_stock` is `False`, `price <= 0`, `country != intent.country`, `store != intent.store` (unless `intent.store == StoreFilter.BOTH`), `price > intent.max_budget` (when set), `rating < intent.min_rating` or unrated/zero-review (`rating is None` or `review_count == 0`) when `intent.min_rating` is set, or the offer title matches any term in `intent.exclude_keywords` (case-insensitive / Arabic-normalized). | T1.4, T1.5 |
| R3 | **Stage 1 (Intent-Aware Bilingual Anti-Accessory Filter — P4)** must run immediately after hard filters and before Stage 2: when `intent.include_accessories` is `False`, group bilingual accessory keywords by semantic concept (`cases/covers`, `screen_protectors`, `chargers/adapters`, `cables/cords`, `straps`, `holders/mounts/sleeves/skins`) covering (`case`, `cover`, `protector`, `cable`, `cord`, `charger`, `adapter`, `strap`, `holder`, `mount`, `skin`, `sleeve`, `جراب`, `كفر`, `حافظة`, `شاحن`, `اسكرينة`, `حماية شاشة`, `وصلة`, `كابل`, `سلك`, `حامل`, `سوار`, with optional leading `و` conjunction before `ال` on Arabic multi-word patterns) and reject offers whose normalized title matches any active concept group unless any term in that concept group appears in the normalized `intent.query`, using boundary-aware matching to avoid false rejections on non-accessory words, and record the exact count removed in `RankingResult.filtered_accessories_count`. | T1.6, T1.7, T3.5 |
| R4 | **Stage 2 (Statistical Median Price Guard — P4)** must run after Stage 1 on remaining candidates whenever `len(candidates) >= config.min_candidates_for_outlier_guard` (default `3`): compute the `Decimal` median price of those remaining candidates and reject suspiciously cheap floor outliers (`price < config.price_floor_ratio * median`, default `0.15`) as well as extreme upper price anomalies (`price > config.price_ceiling_ratio * median`, default `3.0`, unless accommodated by `intent.max_budget`), recording the exact count removed in `RankingResult.filtered_outliers_count` (`0` when fewer than `min_candidates_for_outlier_guard` candidates remain). | T1.8, T3.4, T3.5 |
| R5 | **Bayesian Confidence-Adjusted Rating (P3, INV-03)**: When `offer.rating is not None` and `offer.review_count > 0`, compute $R_{\text{adj}} = \frac{v}{v + m} \cdot R + \frac{m}{v + m} \cdot C$ using `m = config.bayesian_prior_count` (`25`) and `C = config.bayesian_prior_mean` (`4.0`); when `offer.rating is None` or `offer.review_count == 0` (eligible when `intent.min_rating is None`), set `bayesian_rating = config.unrated_prior_rating` (`3.4` by default, strictly below `bayesian_prior_mean`) directly. | T1.2, T1.3, T1.4 |
| R6 | **Price Normalization & Single-Candidate Rule (P3, INV-03)**: Across post-Stage-2 surviving candidates, compute $P_{\text{norm}} = \frac{P_{\max} - P}{P_{\max} - P_{\min}}$ when $P_{\max} > P_{\min}$, and set `price_norm = 1.0` whenever $P_{\max} == P_{\min}$ (including single-candidate pools and equal-price sets). | T1.1, T3.3 |
| R7 | **Composite Value Score & Configurable Weights (INV-03)**: Compute $R_{\text{norm}} = R_{\text{adj}} / 5.0$ and $S_{\text{value}} = 100.0 \times (w_{\text{price}} \cdot P_{\text{norm}} + w_{\text{rating}} \cdot R_{\text{norm}})$ using `config.price_weight` (`0.55`) and `config.rating_weight` (`0.45`), applying deterministic rounding (`round(..., 2)` for `value_score`, `round(..., 4)` for `price_norm` and `bayesian_rating`) so displayed scores and ranking order always agree. | T1.1, T1.9 |
| R8 | **Deterministic Ranking, Tie-Breaking & Top-K Slice**: Sort surviving candidates by descending `value_score`, then descending `offer.review_count`, then ascending `offer.price`, then ascending `offer.offer_id`, and return up to `config.top_k` (`3`) `RankedOffer` items assigned sequential `rank` values starting at `1`. | T1.1, T3.6 |
| R9 | **Deterministic `match_reasons` Labels**: Populate a non-empty `match_reasons: tuple[str, ...]` for every `RankedOffer` using deterministic tags derived from the surviving pool (`"best_overall_value"` for `rank == 1`, `"lowest_price"` for minimum price, `"top_bayesian_rating"` for maximum `bayesian_rating` among rated offers, `"high_review_confidence"` when `review_count >= config.bayesian_prior_count`, `"within_budget"` when `intent.max_budget` is set, `"unrated_fallback"` when the unrated prior applied, and `"strong_value_runner_up"` when no other tag applies to a runner-up). | T1.10 |
| R10 | **Honest Degradation & Zero Hallucination (INV-05, INV-08)**: When `0 <= len(ranked_offers) < config.top_k` (including empty input or total elimination), return the available `0–2` verified offers unmodified inside `RankingResult` with `degraded_fewer_than_k = True` and never raise exceptions or fabricate synthetic items. | T1.10, T3.1, T3.2 |

---

## 2. Non-Functional Requirements

| ID | Requirement | Validated by (validation.md check) |
|:---|:---|:---|
| NFR1 | **Pure Deterministic Arithmetic & Speed (`INV-03`, `spec/architecture.md` §4)**: `rank_top_offers` must execute strictly in-process in pure deterministic Python using zero LLM tokens, zero randomness, and `< 2 ms` typical (`< 50 ms` CI wall-clock assertion ceiling to avoid tracing flakiness) per ranking batch (`<= 100` offers), yielding bit-identical outputs on repeated runs. | T1.1, T3.7, T4.1 |
| NFR2 | **Strict Hexagonal Isolation (`INV-02`)**: `commerce_ai.domain.ranking` must import only Python standard library modules, `commerce_ai.domain.models`, and `commerce_ai.config`, with zero vendor SDK, HTTP, cache, database, or `commerce_ai.adapters` dependencies. | T1.11, T5.1, T5.3 |
| NFR3 | **100% Offline Test Determinism (`INV-07`)**: All unit and edge-case tests in `backend/tests/unit/test_ranking.py` must execute 100% offline with zero paid API keys, network sockets, or external services. | T3.7, T4.1 |
| NFR4 | **Code Quality & Strict Static Typing (`spec/sdd-profile.md`)**: Feature 1.2 source and tests must pass `ruff check .`, `ruff format --check .`, and `mypy src` cleanly with full type annotations. | T5.1, T5.2, T5.3 |

---

## 3. Constraints (must NOT do / change)

- **C1**: Must respect `spec/tech.md` invariant `INV-02` (Strict Ports & Adapters — zero vendor SDK or adapter imports in `domain/ranking.py`).
- **C2**: Must respect `spec/tech.md` invariant `INV-03` (Deterministic Math & Configurable Scoring — never delegate scoring to LLM calls or hardcode non-overridable weights).
- **C3**: Must respect `spec/tech.md` invariant `INV-05` (Zero Hallucinated Offers — never mutate `ProductOffer` attributes or invent filler offers).
- **C4**: Must respect `spec/tech.md` invariant `INV-07` (100% Offline Deterministic Test Suite — zero network calls or external API dependencies).
- **C5**: Must respect `spec/tech.md` invariant `INV-08` (Graceful Degradation — `0–2` qualifying items set `degraded_fewer_than_k=True` without crashing).
- **C6**: Must strictly uphold `P7` Disjoint File Partition — create/own ONLY `backend/src/commerce_ai/domain/ranking.py` and `backend/tests/unit/test_ranking.py`; MUST NOT modify `backend/pyproject.toml`, `backend/src/commerce_ai/domain/__init__.py`, `backend/src/commerce_ai/domain/models.py`, `backend/src/commerce_ai/config/*`, `backend/src/commerce_ai/domain/ports.py`, or `backend/src/commerce_ai/adapters/**`.
- **C7**: Must NOT create application code or edit `spec/roadmap.md` before Phase Gate 1 approval.

---

## 4. Dependencies & Assumptions

- **Depends on**:
  - **Feature 1.1** (`spec/features/feature-101-backend-scaffold-domain-models/`): provides `backend/pyproject.toml`, `domain/__init__.py`, `ProductOffer`, `SearchIntent`, `RankedOffer`, `RankingResult`, `StoreFilter` (`commerce_ai.domain.models`), and `ScoringConfig` (`commerce_ai.config`).
  - No external services, databases, caches, or environment variables are required by Feature 1.2.
- **Assumptions**:
  - `ProductOffer` validates positive `Decimal` prices and regional `country`/`currency` consistency at construction time (per `P2` in Feature 1.1); `domain/ranking.py` additionally guards `price > 0` defensively.
  - `ScoringConfig` validates `price_weight + rating_weight == 1.0` (within floating-point tolerance), `top_k >= 1`, and positive Bayesian/outlier parameters in Feature 1.1.
