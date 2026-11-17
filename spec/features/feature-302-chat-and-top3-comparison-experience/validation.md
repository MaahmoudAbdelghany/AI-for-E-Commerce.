# Validation Criteria: Feature 3.2 — Interactive Shopping Chat & Top-3 Comparison Experience

> Status: Draft (Pending Phase Gate 1 Approval)

## 1. Success Definition

Feature 3.2 is complete when all 9 workspace components under `frontend/src/components/workspace/` are wired inside `<AppShell>` via `frontend/src/app/page.tsx`, shoppers can converse via `POST /api/v1/chat`, switch seamlessly via `ModeToggle` to Zero-LLM Direct Search (`POST /api/v1/search`, `0` LLM calls) with `min_rating` and `include_accessories`, trigger `"قارن أفضل العروض / Compare Saved Offers"` when `>= 2` verified offers are saved, inspect strictly server-ordered Top-3 `OfferCard` items with zero client math/padding and verified `https://` links/images (`INV-03`, `INV-05`, `INV-09`), see transparent `TelemetryStrip` provenance/cost metrics and accessible bilingual `StatusBanner` degradation/retry states (`INV-08`), and all Vitest unit/integration tests (`tests/unit/offer-card-and-banners.test.tsx`, `tests/integration/shopping-workspace.test.tsx`), `npm --prefix frontend test`, `npm --prefix frontend run lint && npm --prefix frontend run typecheck`, `npm --prefix frontend run build` (offline, `INV-07`), `uv run --no-sync --directory backend pytest -v`, and Tier 7 full-stack HTTP verification pass with zero errors while Tier 6 manual browser RTL/LTR & `375px`/`1280px` checks remain explicitly documented for human verification.

---

## 2. Requirement Traceability

### 2.1 Requirements → Checks

| Requirement | Checks |
| :--- | :--- |
| R1 | T2.5, T6.1, T6.2, T7.1 |
| R2 | T2.1, T2.2, T6.1 |
| R3 | T2.2, T3.1, T7.1 |
| R4 | T2.1, T2.4, T3.2, T6.1 |
| R5 | T2.1, T2.3, T3.1, T3.2, T6.1 |
| R6 | T2.1, T2.4, T6.1 |
| R7 | T1.4, T2.1, T2.2, T2.3, T3.4 |
| R8 | T1.1, T1.2, T2.4 |
| R9 | T1.3, T6.1 |
| R10 | T1.5, T2.1, T2.2, T2.3 |
| R11 | T1.6, T3.3, T3.4, T3.5 |
| R12 | T2.4, T3.2, T3.3 |
| NFR1 | T1.1, T1.2, T1.4, T3.4 |
| NFR2 | T1.3, T1.6, T3.3 |
| NFR3 | T1.1, T1.6, T2.4, T6.1, T6.2 |
| NFR4 | T1.1, T1.2, T1.3, T1.4, T1.5, T1.6, T2.1, T2.2, T2.3, T2.4, T2.5, T3.1, T3.2, T3.3, T3.4, T3.5, T4.1, T5.3 |
| NFR5 | T4.1, T4.2, T5.1, T5.2, T5.3, T7.1 |

### 2.2 Checks → Requirements

| Check | Requirements Covered |
| :--- | :--- |
| T1.1 | R8, NFR1, NFR3, NFR4 |
| T1.2 | R8, NFR1, NFR4 |
| T1.3 | R9, NFR2, NFR4 |
| T1.4 | R7, NFR1, NFR4 |
| T1.5 | R10, NFR4 |
| T1.6 | R11, NFR2, NFR3, NFR4 |
| T2.1 | R2, R4, R5, R6, R7, R10, NFR4 |
| T2.2 | R2, R3, R7, R10, NFR4 |
| T2.3 | R5, R7, R10, NFR4 |
| T2.4 | R4, R6, R8, R12, NFR3, NFR4 |
| T2.5 | R1, NFR4 |
| T3.1 | R3, R5, NFR4 |
| T3.2 | R4, R5, R12, NFR4 |
| T3.3 | R11, R12, NFR2, NFR4 |
| T3.4 | R7, R11, NFR1, NFR4 |
| T3.5 | R11, NFR4 |
| T4.1 | NFR4, NFR5 |
| T4.2 | NFR5 |
| T5.1 | NFR5 |
| T5.2 | NFR5 |
| T5.3 | NFR4, NFR5 |
| T6.1 | R1, R2, R4, R5, R6, R9, NFR3 |
| T6.2 | R1, NFR3 |
| T7.1 | R1, R3, NFR5 |

---

## 3. Verification Tiers

### Tier 1: Unit Verification

- [ ] **T1.1 — `OfferCard` Grounded Rendering & All 7 `match_reasons` (`R8`, `NFR1`, `NFR3`, `NFR4`)**: Render `OfferCard` in both `"ar"` and `"en"` for `RankedOffer` fixtures covering `noon` and `amazon`, exact `DecimalString` prices (`"3299.00"` `EGP`), `rating`/`review_count`, `bayesian_rating`, `value_score` progress bar (`role="progressbar"`), and all 7 domain `match_reasons` (`best_overall_value`, `lowest_price`, `top_bayesian_rating`, `high_review_confidence`, `within_budget`, `unrated_fallback`, `strong_value_runner_up`) → verifies rank badge `#1..#3`, localized store badge (`نون`/`Noon`, `أمازون`/`Amazon`), exact decimal formatting via `formatExactPrice` without rounding/math alteration, `X.XX / 5.0` Bayesian label, `XX.X / 100` bar, and localized labels for all 7 reason codes (`frontend/tests/unit/offer-card-and-banners.test.tsx::OfferCard renders grounded price, Bayesian rating, value bar, store badge, and all 7 bilingual match reasons`).
- [ ] **T1.2 — `OfferCard` Explicit Unrated Edge Case (`R8`, `NFR1`, `NFR4`)**: Render `OfferCard` with `{ rating: null, review_count: 0 }` and `{ rating: 4.5, review_count: 0 }` → verifies `"غير مُقيّم / Unrated"` badge renders without fabricated stars or fake review counts (`frontend/tests/unit/offer-card-and-banners.test.tsx::OfferCard renders explicit Unrated badge when rating is null or review_count is 0`).
- [ ] **T1.3 — `OfferCard` Strict `https://` Image Fallback & Safe Outbound CTA (`R9`, `NFR2`, `NFR4`)**: Render `OfferCard` with valid `https://` `image_url`/`url`, `image_url: null`, `http://` / `javascript:` / embedded-credential URLs, and simulated `<img>` `onError` → valid `https://` image renders `<img loading="lazy" referrerPolicy="no-referrer">`; `null`, unsafe, or errored images switch cleanly to an inline SVG product icon fallback via `sanitizeHttpsUrl`; valid `https://` `offer.url` renders `<a target="_blank" rel="noopener noreferrer">`; unsafe `offer.url` disables the outbound CTA without emitting an unsafe `href` (`frontend/tests/unit/offer-card-and-banners.test.tsx::OfferCard enforces strict https image fallback and noopener noreferrer outbound CTA guard`).
- [ ] **T1.4 — `ProductComparisonGrid` Server-Order Fidelity & Zero Fake Padding (`R7`, `NFR1`, `NFR4`)**: Render `ProductComparisonGrid` with 3 offers whose prices/scores deliberately differ from numeric order and with `1` or `2` offers when `degraded_fewer_than_k === true` → verifies cards appear strictly in server-returned order (`rank` `1`, `2`, `3`) with zero client-side re-sorting and renders strictly `1` or `2` cards with zero synthetic placeholder cards (`frontend/tests/unit/offer-card-and-banners.test.tsx::ProductComparisonGrid preserves exact server rank order without client sorting or fake padding`).
- [ ] **T1.5 — `TelemetryStrip` Provenance, Cache, LLM Calls & Filter Counts (`R10`, `NFR4`)**: Render `TelemetryStrip` for `sourceMode="seed"` (`cacheHit=false`, `llmCalls=1`), `sourceMode="live"` (`cacheHit=true`, `llmCalls=0`), and saved-offer comparison (`sourceMode=null`, `rankingResult=null`) → verifies localized Seed Demo vs Live Search labels, Cache Hit/Miss, LLM Calls count, `latencyMs` (`formatLatencyMs`), `requestId`, and `total_candidates`, `filtered_accessories_count`, and `filtered_outliers_count` (`frontend/tests/unit/offer-card-and-banners.test.tsx::TelemetryStrip displays source mode, cache hit/miss, LLM calls, latency, request_id, and filter counts`).
- [ ] **T1.6 — `StatusBanner` Exhaustive Bilingual Degradation & Privacy States (`R11`, `NFR2`, `NFR3`, `NFR4`)**: Render `StatusBanner` in `"ar"` and `"en"` for `clarify`, `off_topic`, `refused`, `degraded`, `degraded_fewer_than_k === true`, `0` qualifying offers, HTTP `429` (`Retry-After: 12`), and HTTP `503`/network failure → verifies distinct `role="status"` vs `role="alert"` semantics, `Retry-After` seconds display, working Retry callback, and zero sensitive input echo on `refused` (`frontend/tests/unit/offer-card-and-banners.test.tsx::StatusBanner renders accessible bilingual banners for clarify, off_topic, refused, degraded, partial, empty, 429, and 503 with retry`).

### Tier 2: Integration Verification

- [ ] **T2.1 — Default Chat Flow & Market-Localized `StarterPrompts` (`R2`, `R4`, `R5`, `R6`, `R7`, `R10`, `NFR4`)**: Mount `<ShopSessionProvider>` + `<ShoppingWorkspace />` with mocked `api.ts` / `fetch` (zero live HTTP) in default `"ar"` / `"EG"` Chat mode → click a localized `StarterPrompts` chip (`EG` Anker earbuds) and submit a follow-up via `MessageComposer` → asserts `sendChatTurn` receives `{ message, country: "EG", store: "both", language: "ar" }`, `ChatThread` displays bilingual user & assistant bubbles with `action`/`status` metadata, `ProductComparisonGrid` + `TelemetryStrip` update with Top-3 offers, and `localStorage` (`commerce_ai.market_sessions.v1`) saves `sessionId` and `activeComparison` (`frontend/tests/integration/shopping-workspace.test.tsx::default chat mode starter prompts and Enter/Send update ChatThread, Top-3 grid, telemetry, and session storage`).
- [ ] **T2.2 — `ModeToggle` & Zero-LLM Direct Search Flow (`R2`, `R3`, `R7`, `R10`, `NFR4`)**: Switch via `ModeToggle` to Zero-LLM Direct Search → set query (`"air fryer"`), select `min_rating = 4.5`, toggle `include_accessories = true`, and submit → asserts `searchOffers` is called with exact parameters (`0` `sendChatTurn` calls), unified `ProductComparisonGrid` updates with ranked results, `TelemetryStrip` shows `0` LLM calls, and toggling back to Chat preserves the active market thread and offers (`frontend/tests/integration/shopping-workspace.test.tsx::ModeToggle switches to zero-LLM Direct Search with min_rating and include_accessories feeding unified comparison grid`).
- [ ] **T2.3 — `"قارن أفضل العروض / Compare Saved Offers"` Quick Action (`R5`, `R7`, `R10`, `NFR4`)**: Verify Compare Saved Offers button is absent when `< 2` offers are loaded; after a Chat/Direct Search response populates `>= 2` offers, verify button renders in Chat mode; click it → asserts `sendChatTurn` is dispatched with active `sessionId`, `ChatThread` appends comparison response, and `ProductComparisonGrid` + `TelemetryStrip` render cleanly even when `ranking_result === null` and `telemetry.catalog_source_mode === null` (`ActiveComparisonState.rankingResult === null`, `sourceMode === null`) (`frontend/tests/integration/shopping-workspace.test.tsx::Compare Saved Offers button appears only with >= 2 offers and dispatches comparison chat turn cleanly`).
- [ ] **T2.4 — Bilingual RTL/LTR Switching & Per-Market Session Isolation (`R4`, `R6`, `R8`, `R12`, `NFR3`, `NFR4`)**: Populate `EG` session, switch `country` selector to `SA` (`AppShell` + `ShoppingWorkspace`), and toggle language from `"ar"` (`dir="rtl"`) to `"en"` (`dir="ltr"`) → verifies `SA` displays its own isolated `ChatThread`, `StarterPrompts`, and empty/independent comparison state without showing `EG` offers, and all workspace headings/badges/reasons switch cleanly to English (`frontend/tests/integration/shopping-workspace.test.tsx::per-market isolation separates EG/SA/AE threads and offers while instant ar/en toggle updates all workspace copy`).
- [ ] **T2.5 — Root Route `src/app/page.tsx` Wiring Inside `<AppShell>` (`R1`, `NFR4`)**: Render `HomePage` (`frontend/src/app/page.tsx`) with mocked `fetchMarkets` / `fetchHealth` → verifies `<ShoppingWorkspace />` mounts cleanly inside `<AppShell>` (replacing Feature 3.1's placeholder), displays market/store/budget/language selectors alongside `ModeToggle`, `StarterPrompts`, and comparison landmark (`#comparison-panel`) (`frontend/tests/integration/shopping-workspace.test.tsx::HomePage renders ShoppingWorkspace cleanly inside AppShell`).

### Tier 3: Error & Edge-Case Verification

- [ ] **T3.1 — Inline Budget Validation & Direct Search Query Guards (`R3`, `R5`, `NFR4`)**: Enter invalid `maxBudget` values (`"-5"`, `"0"`, `"10000001"`, `"not-a-number"`) and attempt Chat/Search submission; also attempt blank or `501`-character Direct Search query → verifies accessible inline `role="alert"` errors appear and mocked `sendChatTurn` / `searchOffers` receive `0` calls (`frontend/tests/integration/shopping-workspace.test.tsx::inline budget and Direct Search query validation block invalid submissions with zero API calls`).
- [ ] **T3.2 — In-Flight Duplicate-Submit Guard & Market-Switch Race Cancellation (`R4`, `R5`, `R12`, `NFR4`)**: Trigger a deferred mocked `sendChatTurn` promise, press `Enter`/Send repeatedly, then switch `country` to `AE` (or click New Chat) before the deferred promise resolves → verifies only `1` API call was issued while loading skeleton rendered, and resolving the stale `EG` promise never overwrites `AE` session or comparison cards (`frontend/tests/integration/shopping-workspace.test.tsx::in-flight guard blocks duplicate submits and ignores stale responses after market switch or New Chat`).
- [ ] **T3.3 — Chat Non-Nominal Statuses & PII Refusal Non-Persistence (`R11`, `R12`, `NFR2`, `NFR4`)**: Drive mocked `ChatResponse` returns for `clarify`, `off_topic`, `refused` (submitting a test card string `"4111111111111111"`), and `degraded` after a successful Top-3 search → verifies corresponding `StatusBanner` renders, prior valid comparison offers remain visible on `clarify`/`off_topic`/`refused`, and `"4111111111111111"` never appears in `StatusBanner`, assistant reply, or `localStorage["commerce_ai.market_sessions.v1"]` (`frontend/tests/integration/shopping-workspace.test.tsx::handles clarify, off_topic, refused without PII persistence, and degraded chat states`).
- [ ] **T3.4 — Partial (`< 3`) & `0`-Offer Honest Degradation (`R7`, `R11`, `NFR1`, `NFR4`)**: Return `degraded_fewer_than_k: true` with `2` offers, then return `0` offers (`ranked_offers: []`) → verifies `2`-offer response renders strictly `2` cards + partial banner (zero fake 3rd card), and `0`-offer response clears stale cards and displays the `0` qualifying offers banner (`frontend/tests/integration/shopping-workspace.test.tsx::renders partial < 3 offers without fake padding and clears stale offers on 0 results`).
- [ ] **T3.5 — HTTP `429` (`Retry-After`) & `503`/Network Outage + Retry Recovery (`R11`, `NFR4`)**: Reject `sendChatTurn` / `searchOffers` with `ApiClientError(status=429, retryAfterSeconds=15)` and `ApiClientError(status=503, errorCode="backend_unreachable", retriable=true)` -> click `StatusBanner` Retry button -> resolves with HTTP `200` offers → verifies `Retry-After` guidance, outage banner, and clean state recovery upon retry (`frontend/tests/integration/shopping-workspace.test.tsx::displays 429 Retry-After and 503 outage banners and recovers via Retry action`).

### Tier 4: Regression Checks

- [ ] **T4.1 — Full Offline Frontend Test Suite (`NFR4`, `NFR5`)**: Run `npm --prefix frontend test` (`vitest run`) → all Feature 3.1 and Feature 3.2 unit & integration tests pass 100% offline with zero skipped or relaxed assertions.
- [ ] **T4.2 — Full Offline Backend Regression Suite (`NFR5`)**: Run `uv run --no-sync --directory backend pytest -v` → all Phase 1 and Phase 2 tests remain 100% green (`backend/` untouched per `P7`).

### Tier 5: Build, Lint & Type Checks

- [ ] **T5.1 — Frontend ESLint Check (`NFR5`)**: Run `npm --prefix frontend run lint` (`eslint src tests`) → passes with zero errors or warnings.
- [ ] **T5.2 — Frontend Strict TypeScript Check (`NFR5`)**: Run `npm --prefix frontend run typecheck` (`tsc --noEmit` with `strict: true` and `noUncheckedIndexedAccess: true`) → passes with zero type errors.
- [ ] **T5.3 — Offline Next.js Production Build (`NFR4`, `NFR5`, `INV-07`)**: Run `npm --prefix frontend run build` (`next build` without internet access or `next/font/google`) → completes cleanly with zero build errors.

### Tier 6: Manual / Visual Verification

- [ ] **T6.1 — Desktop (`1280x800`) Arabic RTL & English LTR Dual-Mode Walkthrough (`R1`, `R2`, `R4`, `R5`, `R6`, `R9`, `NFR3`)**:
  - Launch backend (`uv run --no-sync --directory backend uvicorn commerce_ai.main:app --port 8000`) and frontend (`npm --prefix frontend run dev`), open `http://localhost:3000` at `1280x800`.
  - Expect: Arabic (`dir="rtl"`, `lang="ar"`) 2-column desktop layout (`Chat`/`Search` pane + sticky Top-3 grid), zero horizontal scroll. Click an `EG` Starter Prompt (Anker earbuds) → verify `ChatThread` bubble, Top-3 `OfferCard` badges/price/Bayesian rating/value bar/reasons, `TelemetryStrip` (`Seed Demo`), and `<a target="_blank" rel="noopener noreferrer">` store link; click **"قارن أفضل العروض"**; toggle to Direct Search and run a query with `min_rating=4.5` & `include_accessories`; toggle `LanguageToggle` to English (`dir="ltr"`, `lang="en"`) and confirm clean layout parity.
- [ ] **T6.2 — Mobile (`375x812`) Responsive & Overflow Check (`R1`, `NFR3`)**:
  - Switch DevTools viewport to `375x812` in both `RTL` (`ar`) and `LTR` (`en`).
  - Expect: `document.documentElement.scrollWidth <= window.innerWidth` (zero horizontal overflow), visible quick-jump button/link scrolling to `#comparison-panel`, clean stacked `OfferCard` wrapping on long bilingual titles, and accessible `StatusBanner` readability.

### Tier 7: API / CLI / Application Checks

- [ ] **T7.1 — Full-Stack Production Server HTTP Smoke Check (`R1`, `R3`, `NFR5`)**:
  - Start FastAPI backend (`uvicorn commerce_ai.main:app --host 127.0.0.1 --port 8000` with offline `SeedCatalogProvider` defaults) and production Next.js frontend (`npm --prefix frontend run build && npm --prefix frontend run start -- --port 3000`) non-interactively, issue HTTP requests via `Invoke-WebRequest` / `curl` against:
    - `GET http://127.0.0.1:3000/` → HTTP `200` SSR HTML containing workspace markup.
    - `POST http://127.0.0.1:3000/api/v1/chat` (body `{"message":"سماعة بلوتوث أنكر","country":"EG","store":"both","language":"ar"}`) → HTTP `200` `ChatResponse` with verified Top-3 offers.
    - `POST http://127.0.0.1:3000/api/v1/search` (body `{"query":"air fryer","country":"EG","store":"both","min_rating":4.5,"include_accessories":false,"language":"en"}`) → HTTP `200` `SearchResponse` with `degraded_fewer_than_k: true` and `2` offers.
  - Stop both background processes cleanly after verification.

### Extra Gates (from `spec/sdd-profile.md`)

- **Status: Not Applicable**
- **Technical justification**: Per `spec/sdd-profile.md`, `uv run --directory backend pytest tests/evals -v` becomes mandatory from **Feature 4.1** onward once the golden Arabic/English backend evaluation dataset is introduced; Feature 3.2 authors exclusively frontend React workspace UI components (`frontend/src/components/workspace/*`, `frontend/src/app/page.tsx`) and offline Vitest tests (`frontend/tests/`) without modifying `backend/` or LLM prompts/pipelines.

---

## 4. Automated Execution Commands

```text
npm --prefix frontend test -- tests/unit/offer-card-and-banners.test.tsx tests/integration/shopping-workspace.test.tsx
npm --prefix frontend test
npm --prefix frontend run lint && npm --prefix frontend run typecheck
npm --prefix frontend run build
uv run --no-sync --directory backend pytest -v
```

---

## 5. Execution Results (filled in execute mode)

| Check | Result (✅ / ❌ / ⏭ N/A) | Evidence (command output summary, counts) |
| :--- | :--- | :--- |
| `T1.1`–`T1.6` (Unit) | [ ] | Pending implementation (`npm --prefix frontend test -- tests/unit/offer-card-and-banners.test.tsx`) |
| `T2.1`–`T2.5` (Integration) | [ ] | Pending implementation (`npm --prefix frontend test -- tests/integration/shopping-workspace.test.tsx`) |
| `T3.1`–`T3.5` (Error & Edge) | [ ] | Pending implementation (`npm --prefix frontend test -- tests/integration/shopping-workspace.test.tsx`) |
| `T4.1` (Frontend Regression) | [ ] | Pending implementation (`npm --prefix frontend test`) |
| `T4.2` (Backend Regression) | [ ] | Pending implementation (`uv run --no-sync --directory backend pytest -v`) |
| `T5.1` (Lint) | [ ] | Pending implementation (`npm --prefix frontend run lint`) |
| `T5.2` (Typecheck) | [ ] | Pending implementation (`npm --prefix frontend run typecheck`) |
| `T5.3` (Offline Build) | [ ] | Pending implementation (`npm --prefix frontend run build`) |
| `T6.1`–`T6.2` (Manual Browser RTL/LTR & Responsive) | [ ] | Pending human browser verification at `1280x800` and `375x812` |
| `T7.1` (Full-Stack HTTP Smoke) | [ ] | Pending implementation (FastAPI + Next.js production server HTTP verification) |
| `Extra Gates` (`tests/evals`) | [ ] | Not Applicable until Feature 4.1 per `spec/sdd-profile.md` |
