# Validation Criteria: Feature 3.1 — Arabic-First RTL App Shell, Selectors & Typed API Client

> Status: Draft (Pending Phase Gate 1 Approval)

## 1. Success Definition

Feature 3.1 is complete when `frontend/` initializes cleanly with `package.json`, `package-lock.json`, strict TypeScript (`strict: true`, `noUncheckedIndexedAccess: true`), non-interactive flat ESLint, Tailwind CSS, and native Arabic/English typography (zero `next/font/google`, `INV-07`), `src/lib/{contracts,api,proxy,i18n,format,storage}.ts` and runtime Route Handlers (`/api/v1/[...path]`, `/api/health`) pass all offline unit and integration checks in `frontend/tests/unit/{api.test.ts,storage-and-format.test.ts}` and `frontend/tests/integration/{proxy-routes.test.ts,app-shell.test.tsx}` with zero live network calls, `npm --prefix frontend run lint`, `npm --prefix frontend run typecheck`, `npm --prefix frontend run build`, `npm --prefix frontend test`, `uv run --no-sync --directory backend pytest -v`, and Tier 7 full-stack HTTP verification against FastAPI + Next.js all pass without error, while Tier 6 manual browser checks are prepared cleanly for human visual sign-off.

---

## 2. Requirement Traceability

### 2.1 Requirements → Checks

| Requirement | Checks |
| :--- | :--- |
| R1 | T4.1, T5.1, T5.2, T5.3, T5.4 |
| R2 | T2.4, T5.3, T6.1 |
| R3 | T1.1, T5.2, T7.1 |
| R4 | T1.1, T1.2, T3.1, T3.2 |
| R5 | T2.1, T2.2, T3.3, T3.4, T7.1 |
| R6 | T1.3, T2.4, T5.2 |
| R7 | T1.3, T3.5 |
| R8 | T1.4, T2.3, T3.6 |
| R9 | T2.3, T2.4, T3.6, T6.1 |
| R10 | T2.4, T3.6, T6.1, T6.2, T7.1 |
| NFR1 | T4.1, T4.2, T5.3 |
| NFR2 | T1.3, T2.2, T3.3, T3.4, T3.5 |
| NFR3 | T1.1, T1.3, T2.1, T3.5 |
| NFR4 | T4.2, T5.1, T5.2, T5.4 |
| NFR5 | T2.4, T6.1, T6.2 |

### 2.2 Checks → Requirements

| Check | Requirements Covered |
| :--- | :--- |
| T1.1 | R3, R4, NFR3 |
| T1.2 | R4 |
| T1.3 | R6, R7, NFR2, NFR3 |
| T1.4 | R8 |
| T2.1 | R5, NFR3 |
| T2.2 | R5, NFR2 |
| T2.3 | R8, R9 |
| T2.4 | R2, R6, R9, R10, NFR5 |
| T3.1 | R4 |
| T3.2 | R4 |
| T3.3 | R5, NFR2 |
| T3.4 | R5, NFR2 |
| T3.5 | R7, NFR2, NFR3 |
| T3.6 | R8, R9, R10 |
| T4.1 | R1, NFR1 |
| T4.2 | NFR1, NFR4 |
| T5.1 | R1, NFR4 |
| T5.2 | R1, R3, R6, NFR4 |
| T5.3 | R1, R2, NFR1 |
| T5.4 | R1, NFR4 |
| T6.1 | R2, R9, R10, NFR5 |
| T6.2 | R10, NFR5 |
| T7.1 | R3, R5, R10 |

---

## 3. Verification Tiers

### Tier 1: Unit Verification

- [x] **T1.1 — Typed API Client Requests & `DecimalString` Contract Parity**: Mock `globalThis.fetch` and invoke `fetchMarkets`, `fetchHealth`, `sendChatTurn`, and `searchOffers` with relative default config → issues `GET /api/v1/markets`, `GET /api/health`, `POST /api/v1/chat`, and `POST /api/v1/search` with exact JSON payloads and preserves backend `DecimalString` prices (`"3299.00"`) and `RankedOffer` ordering verbatim (`frontend/tests/unit/api.test.ts::"typed client calls relative proxy routes and preserves DecimalString contracts"`).
- [x] **T1.2 — `ApiClientError` Parsing (`422`, `429` + `Retry-After`, `503`, Non-JSON)**: Mock non-2xx `ErrorResponse` payloads including HTTP `422` (`details`), `429` (`Retry-After: 45`), `503` (`backend_unreachable`), and non-JSON `502` HTML → throws `ApiClientError` populated with `status`, `errorCode`, `retriable`, `requestId`, `retryAfterSeconds`, and `details` (`frontend/tests/unit/api.test.ts::"ApiClientError parses ErrorResponse, Retry-After, and non-JSON fallbacks"`).
- [x] **T1.3 — Loss-Free Price Formatting, Complete Bilingual Dictionary & Strict `https://` Guard (`INV-05`, `INV-09`)**: Format `DecimalString` values (`"3299.00"`, `"9999999.99"`) in `ar` and `en`, inspect `i18n.ts` dictionaries for all 7 `match_reasons` codes, `TurnStatus` banners, `429`/`503` messages, and `EG`/`SA`/`AE` `STARTER_PROMPTS`, and validate URLs with `sanitizeHttpsUrl` → preserves exact decimal digits without float drift, covers every key in both `ar` and `en`, accepts clean `https://` URLs, and returns `null` for `http://`, `javascript:alert(1)`, `data:`, embedded credentials, backslashes, and whitespace/control characters (`frontend/tests/unit/storage-and-format.test.ts::"formatExactPrice preserves Decimal digits, i18n covers all codes, and sanitizeHttpsUrl enforces https"`).
- [x] **T1.4 — Isolated Per-Market Storage & SSR Safety (`P4`)**: Persist and reload `commerce_ai.prefs.v1` and `commerce_ai.market_sessions.v1` across `EG`, `SA`, and `AE`, plus invoke storage helpers with `window` undefined (SSR) → each market retains isolated `sessionId`, `messages`, and `activeComparison`, and SSR calls return defaults without throwing (`frontend/tests/unit/storage-and-format.test.ts::"storage isolates EG/SA/AE market sessions and works safely under SSR"`).

### Tier 2: Integration Verification

- [x] **T2.1 — Dynamic `/api/v1/[...path]` Allowlisted Proxy & Header/Status Pass-Through**: Invoke `GET` (`["markets"]`) and `POST` (`["chat"]`, `["search"]`) handlers with custom runtime `process.env.BACKEND_API_URL` and mocked `fetch` → confirms `dynamic === "force-dynamic"`, requests target `${BACKEND_API_URL}/api/v1/...`, forwards `Accept`, `Content-Type`, safe `X-Request-ID`, and `X-Forwarded-For`, and preserves upstream HTTP `200`/`422`/`429`, `X-Request-ID`, `Retry-After`, and JSON body untouched (`frontend/tests/integration/proxy-routes.test.ts::"v1 proxy forwards allowlisted routes and passes upstream headers/status through"`).
- [x] **T2.2 — Dynamic `/api/health` Proxy & Outage Mapping (`INV-01`, `INV-08`)**: Invoke `GET` handler in `src/app/api/health/route.ts` with healthy and failing mocked `fetch` → confirms `dynamic === "force-dynamic"`, forwards `GET ${BACKEND_API_URL}/health`, returns upstream `HealthResponse`, and maps network/timeout failure to HTTP `503` `ErrorResponse(error_code="backend_unreachable", retriable=true)` without leaking `BACKEND_API_URL` or stack traces (`frontend/tests/integration/proxy-routes.test.ts::"health proxy forwards runtime /health and maps outage to sanitized 503"`).
- [x] **T2.3 — `ShopSessionProvider` Hydration, Market Isolation & `New Chat` Scope (`P4`)**: Mount `<ShopSessionProvider>` + `<AppShell>` with mocked `fetch` for `/api/v1/markets` and `/api/health` → verifies `EG`/`both`/`ar` initial defaults, market hydration, switching `EG` ↔ `SA` isolates active session & offers, changing `StoreFilterBar` or `BudgetCapControl` preserves active `sessionId`, and clicking **New Chat** clears only the active market session (`frontend/tests/integration/app-shell.test.tsx::"ShopSessionProvider hydrates markets/health, isolates EG/SA/AE sessions, and preserves sessionId on store/budget change"`).
- [x] **T2.4 — Instant `RTL` (`ar`) ↔ `LTR` (`en`) Switching & Root Document Sync (`P4`)**: Mount `<AppShell>` inside `<ShopSessionProvider>` → asserts initial `document.documentElement.lang === "ar"` and `dir === "rtl"` with Arabic labels, clicks `<LanguageToggle>` → updates `document.documentElement.lang === "en"`, `dir === "ltr"`, and all shell labels immediately without page reload, then toggles back to `ar`/`rtl` (`frontend/tests/integration/app-shell.test.tsx::"LanguageToggle switches dir=rtl/ltr and document lang without reload and renders RTL layout"`).

### Tier 3: Error & Edge-Case Verification

- [x] **T3.1 — Client Budget Guard & Network/Abort Failure Handling**: Pass `max_budget <= 0`, `> 10000000.00`, `"NaN"`, `"1e50"`, and simulate `fetch` rejection/`AbortError` in `api.ts` → rejects invalid budgets prior to `fetch` and converts network/abort failures into retriable `ApiClientError(errorCode="network_error", retriable=true)` (`frontend/tests/unit/api.test.ts::"api client validates max_budget bounds client-side and wraps fetch network errors"`).
- [x] **T3.2 — Optional `NEXT_PUBLIC_API_BASE_URL` Normalization**: Configure `NEXT_PUBLIC_API_BASE_URL="http://localhost:8000/"` → strips trailing slash cleanly and routes `fetchMarkets` to `http://localhost:8000/api/v1/markets` and `fetchHealth` to `http://localhost:8000/health` (`frontend/tests/unit/api.test.ts::"api client handles explicit NEXT_PUBLIC_API_BASE_URL trailing slashes cleanly"`).
- [x] **T3.3 — Proxy Rejection of Non-Allowlisted Paths, Traversal & Wrong Methods**: Send `GET /api/v1/admin`, `GET /api/v1/openapi.json`, traversal segments (`..`, `%2e%2e`), `POST /api/v1/markets`, `GET /api/v1/chat`, and `DELETE /api/v1/search` to `/api/v1/[...path]` → returns HTTP `404` `ErrorResponse(error_code="route_not_found")` or HTTP `405` `ErrorResponse(error_code="method_not_allowed")` with `Allow` header and makes `0` upstream `fetch` calls (`frontend/tests/integration/proxy-routes.test.ts::"v1 proxy rejects non-allowlisted paths, traversal segments, and wrong HTTP methods"`).
- [x] **T3.4 — Proxy Timeout/Refusal Sanitized `503` Envelope (`INV-01`, `INV-08`)**: Simulate `ECONNREFUSED` and `TimeoutError` on `/api/v1/chat` with `BACKEND_API_URL="http://secret-internal-host:8000"` → returns HTTP `503` `ErrorResponse(error_code="backend_unreachable", retriable=true)` containing zero internal host/port or stack-trace strings (`frontend/tests/integration/proxy-routes.test.ts::"v1 proxy returns sanitized 503 backend_unreachable on timeout or connection failure"`).
- [x] **T3.5 — `validateBudgetInput` Edge & Boundary Cases**: Validate `""`, `"   "`, `"0"`, `"-5"`, `"10000000.01"`, `"1e50"`, `"abc"`, and `"2499.95"` → accepts empty (`null`) and `"2499.95"` while rejecting zero, negative, oversized, exponential, and non-numeric values (`frontend/tests/unit/storage-and-format.test.ts::"validateBudgetInput and formatExactPrice reject malformed/out-of-range inputs cleanly"`).
- [x] **T3.6 — Corrupted `localStorage` Recovery, Fallback Markets & Inline Budget Alert**: Inject malformed JSON into `commerce_ai.prefs.v1` / `commerce_ai.market_sessions.v1`, return `503` from mocked `/api/v1/markets` and `/api/health`, and type `"-50"` into `BudgetCapControl` → storage recovers cleanly to defaults, `<AppShell>` renders `MARKET_REGISTRY_FALLBACK` + offline `HealthBadge`, and `BudgetCapControl` renders `aria-invalid="true"` with an accessible validation alert (`frontend/tests/unit/storage-and-format.test.ts` + `frontend/tests/integration/app-shell.test.tsx`).

### Tier 4: Regression Checks

- [x] **T4.1 — Full Offline Frontend Test Suite (`INV-07`)**: Run `npm --prefix frontend test` (`vitest run`) → all Feature 3.1 unit and integration suites pass 100% offline with zero skipped or relaxed assertions.
- [x] **T4.2 — Full Offline Backend Test Suite & Partition Integrity (`INV-07`, `P7`)**: Run `uv run --no-sync --directory backend pytest -v` → all existing backend unit and integration tests pass completely offline with zero backend modifications (`git diff --name-only` shows only Feature 3.1 paths).

### Tier 5: Build, Lint & Type Checks

- [x] **T5.1 — Non-Interactive ESLint Check**: `npm --prefix frontend run lint` (`eslint src tests`) passes with zero errors, zero warnings, and zero interactive prompts.
- [x] **T5.2 — Strict TypeScript Check**: `npm --prefix frontend run typecheck` (`tsc --noEmit` with `strict: true` and `noUncheckedIndexedAccess: true`) passes with zero errors across `src/` and `tests/`.
- [x] **T5.3 — Offline Next.js Production Build (`INV-07`)**: `npm --prefix frontend run build` (`next build`) succeeds offline with zero `next/font/google` imports and builds `/`, `/api/health`, and `/api/v1/[...path]` cleanly.
- [x] **T5.4 — Lockfile Reproducibility Check (`spec/sdd-profile.md`)**: `npm --prefix frontend ci` installs cleanly from `frontend/package-lock.json` without modifying lockfile or `package.json`.

### Tier 6: Manual / Visual Verification (Human Verification at Gate)

- [ ] **T6.1 — Live Browser Arabic-First RTL & English LTR Shell Inspection**: Launch `uv run --no-sync --directory backend uvicorn commerce_ai.main:app --port 8000` and `npm --prefix frontend run dev`, open `http://localhost:3000` → confirm Arabic-first RTL layout (`dir="rtl"`, `lang="ar"`), crisp native Arabic typography, `MarketSelector` (`EG`/`SA`/`AE`), `StoreFilterBar` (`All`/`Noon`/`Amazon`), `BudgetCapControl` currency label, `HealthBadge` (`Connected`), and instant toggle to `English` (`dir="ltr"`, `lang="en"`) without page reload.
- [ ] **T6.2 — Responsive Desktop (`1280px`) & Mobile (`375px`) Layout Inspection**: Inspect `http://localhost:3000` at `1280px` and `375px` viewport widths → confirm zero horizontal overflow, legible control wrapping, clear invalid-budget inline feedback, and clean keyboard tab focus across selectors and **New Chat**.

### Tier 7: API / CLI / Application Checks

- [x] **T7.1 — Non-Interactive Full-Stack Next.js ↔ FastAPI HTTP Smoke**: Start FastAPI (`CATALOG_MODE=seed`, `LLM_MODE=fake` on `:8000`) and built Next.js (`BACKEND_API_URL=http://127.0.0.1:8000 npm --prefix frontend run start` on `:3000`) → execute non-interactive HTTP checks against `http://127.0.0.1:3000`: `GET /` (`200` containing `lang="ar"` and `dir="rtl"`), `GET /api/health` (`200` `HealthResponse`), `GET /api/v1/markets` (`200` `MarketsResponse` with `EG`/`SA`/`AE`), `POST /api/v1/search` (`200` `SearchResponse`), `POST /api/v1/chat` (`200` `ChatResponse`), `GET /api/v1/unknown` (`404` `ErrorResponse`), then stop FastAPI and confirm `GET /api/health` returns HTTP `503` `ErrorResponse(error_code="backend_unreachable")` before terminating Next.js cleanly.

### Extra Gates (from `spec/sdd-profile.md`)

- **Status: Not Applicable**
- **Technical justification**: Per `spec/sdd-profile.md`, `uv run --directory backend pytest tests/evals -v` becomes mandatory from `Feature 4.1` onward once the golden Arabic/English evaluation dataset suite is introduced; Feature 3.1 builds only the frontend Next.js RTL shell, typed client, and same-origin Route Handler proxies without modifying backend LLM, ranking, or evaluation modules (`P1`, `P7`), and validates all frontend/proxy/contract behavior through Tiers 1–5 and Tier 7.

---

## 4. Automated Execution Commands

```text
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run lint && npm --prefix frontend run typecheck
npm --prefix frontend run build
uv run --no-sync --directory backend pytest -v
```

---

## 5. Execution Results (filled in execute mode)

| Check | Result (✅ / ❌ / ⏭ N/A) | Evidence (command output summary, counts) |
| :--- | :--- | :--- |
| `T1.1`–`T1.4` (Unit) | ✅ | `npm.cmd --prefix frontend test` (`vitest run`) → `tests/unit/api.test.ts` (4/4 tests: `35ms`), `tests/unit/storage-and-format.test.ts` (4/4 tests: `69ms`) — all 8 unit & edge cases passed 100% offline |
| `T2.1`–`T2.4` (Integration) | ✅ | `npm.cmd --prefix frontend test` (`vitest run`) → `tests/integration/proxy-routes.test.ts` (4/4 tests: `83ms`), `tests/integration/app-shell.test.tsx` (3/3 tests: `1035ms`) — all 7 integration & edge cases passed 100% offline |
| `T3.1`–`T3.6` (Error & Edge) | ✅ | Included in `4 passed (4)`, `15 passed (15)` (`3.63s`, zero skipped/relaxed assertions) across `api.test.ts`, `storage-and-format.test.ts`, `proxy-routes.test.ts`, and `app-shell.test.tsx` |
| `T4.1`–`T4.2` (Regression) | ✅ | Frontend: `npm.cmd --prefix frontend test` → `4 passed (4)` files, `15 passed (15)` tests (`3.63s`). Backend: `uv run --no-sync --directory backend pytest -v` → `163 passed, 1 deselected, 1 warning in 69.80s` (`@pytest.mark.live` deselected; zero backend edits) |
| `T5.1`–`T5.4` (Lint / Type / Build / Lockfile) | ✅ | `npm.cmd --prefix frontend ci` → `added 465 packages, and audited 472 packages in 3m` (exit 0); `npm.cmd --prefix frontend run lint` (`eslint src tests`) → exit 0 (0 errors, 0 warnings); `npm.cmd --prefix frontend run typecheck` (`tsc --noEmit` with `strict` + `noUncheckedIndexedAccess`, also verified without `.next`/`next-env.d.ts`) → exit 0; `npm.cmd --prefix frontend run build` (`next build`, 0 `next/font/google` imports) → exit 0 (`/` `2.41 kB`, `/_not-found` `993 B`, `/api/health` `127 B`, `/api/v1/[...path]` `127 B`, `5.8s`) |
| `T6.1`–`T6.2` (Manual / Visual) | Pending | Left `[ ]` unchecked for human visual RTL/LTR (`1280px` & `375px`) verification at Phase Gate 2 |
| `T7.1` (Full-Stack HTTP Smoke) | ✅ | FastAPI (`CATALOG_MODE=seed`, `LLM_MODE=fake` on `:8000`) + Next.js (`BACKEND_API_URL=http://127.0.0.1:8000`, `next start` on `:3000`): `GET /` → `200` (`lang="ar"`, `dir="rtl"`); `GET /api/health` → `200` (`status=ok`, `catalog=seed`, `llm=fake`); `GET /api/v1/markets` → `200` (`EG,SA,AE`); `POST /api/v1/search` → `200` (`source=seed`, `offers=3`, `top1_price=1199.00`); `POST /api/v1/chat` → `200` (`status=ok`, `action=search`, `offers=3`); `GET /api/v1/unknown` → `404` (`route_not_found`); after stopping FastAPI `GET /api/health` → `503` (`backend_unreachable`, `retriable=True`); ports `8000` & `3000` cleanly freed |
| `Extra Gates` (Evals) | ⏭ N/A | `tests/evals/` mandatory from Feature 4.1 onward per `spec/sdd-profile.md` |
