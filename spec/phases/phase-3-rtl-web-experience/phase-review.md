# Post-Validation Review: Phase 3 — Arabic-First (RTL) Next.js Web Experience

- **Phase**: `phase-3-rtl-web-experience`
- **Branch**: `phase/3-rtl-web-experience` (vs `main` at `d9cb3fd`)
- **Status**: APPROVED (Phase Gate 2 approved by human on 2026-11-17; merged into `main` via `--no-ff` at `d2dce6e`)
- **Commit range (`main..HEAD`)**: `89c7262..6512d52` (`6` local commits prior to Step 9 changelog/closeout; `53 files changed, 19674 insertions(+), 5 deletions(-)`)

## Chronological Commit History (`git log --oneline main..HEAD`)

1. `89c7262` — `docs(spec): add Phase 3 specs`
2. `f9cddc3` — `feat(frontend): implement Feature 3.1 RTL shell, selectors, and typed API client`
3. `d5ac91c` — `feat(frontend): implement Feature 3.2 chat and Top-3 comparison experience`
4. `6731281` — `test(phase-3): add end-to-end phase integration tests and PI evidence`
5. `f5e3ecc` — `fix(phase-3): resolve security, architecture, spec-drift, and test review findings`
6. `6512d52` — `docs(spec): add Phase 3 deep review report` *(Step 9 release notes commit & merge into `main` pending)*

---

## 1. Scope & Boundary Audit

- **Delivered Features**:
  - **Feature 3.1 (`spec/features/feature-301-rtl-shell-selectors-and-api-client/`)**: Initialized `frontend/` (`Next.js 15`, `React 19`, `TypeScript` `strict` + `noUncheckedIndexedAccess`, `Tailwind CSS`, non-interactive flat `eslint.config.mjs`, `Vitest` + `jsdom` + Testing Library, `package-lock.json`) with offline-safe native Arabic/English typography (zero `next/font/google` per `INV-07`); exact TypeScript DTOs (`src/lib/contracts.ts`) mirroring `backend/src/commerce_ai/api/schemas.py` & `domain/models.py`; typed `api.ts` client (`ApiClientError`, pre-submit `max_budget` validation); hardened runtime `force-dynamic` Route Handler proxies (`/api/v1/[...path]`, `/api/health`, `src/lib/proxy.ts`); complete bilingual `ar`/`en` dictionary (`src/lib/i18n.ts`); loss-free `DecimalString` price formatting & strict `https://` URL sanitization (`src/lib/format.ts`); SSR-safe per-market `localStorage` isolation with nested schema recovery (`src/lib/storage.ts`); `ShopSessionProvider` (`EG`/`SA`/`AE` isolation, instant `RTL`/`LTR` switching, `MARKET_REGISTRY_FALLBACK`); and Arabic-first shell selectors (`AppShell`, `MarketSelector`, `StoreFilterBar`, `BudgetCapControl`, `LanguageToggle`, `HealthBadge`).
  - **Feature 3.2 (`spec/features/feature-302-chat-and-top3-comparison-experience/`)**: Mounted `<ShoppingWorkspace />` inside `<AppShell>` (`src/app/page.tsx`), pairing **Conversational Assistant (`POST /api/v1/chat`, default)** and **Zero-LLM Direct Search (`POST /api/v1/search`, `0` LLM calls, `min_rating`, `include_accessories`)** inside one responsive `lg:grid-cols-12` RTL-first workspace (`P5`); strictly server-ordered `ProductComparisonGrid` & grounded `OfferCard` (`INV-03`, `INV-05`, `INV-09`: `https://` image fallback + `rel="noopener noreferrer"` store CTA, Unrated / Bayesian badges, `value_score` bar, all 7 localized `match_reasons`); `TelemetryStrip` provenance/cost/filter telemetry; `ChatThread`, `MessageComposer` (`Enter`/`Shift+Enter`, inline budget/query validation, `Compare Saved Offers` gated on active Chat `sessionId !== null && >= 2` offers), `StarterPrompts`; and accessible `StatusBanner` degradation/retry states (`clarify`, `off_topic`, `refused` with PII non-persistence, `degraded`, `< 3` partial, `0` matches, `429`, `503` — `INV-08`, `INV-09`).
- **Sensitive Area & Workspace Boundary Audit (`main..HEAD`)**:
  - `git diff --name-only main..HEAD` modifies `52` scoped files (`44` files under `frontend/**`, `7` feature/phase spec files under `spec/`, plus `spec/roadmap.md` ticking `[x]` on Feature 3.1 & 3.2).
  - Touches **0** files in `backend/**`, **0** files in `spec/sdd-profile.md` Sensitive Areas (`infra/aws/**`, `.github/workflows/**`, `backend/src/commerce_ai/config/security*`, `backend/migrations/**`), **0** edits to `CHANGELOG.md`, and **0** edits to constitution files (`spec/architecture.md`, `spec/tech.md`, `spec/sdd-profile.md`).
  - `spec/sdd-profile.md` frontend script confirmation (`ci`, `lint`, `typecheck`, `build`, `dev`, `start`, plus adding `npm --prefix frontend test`) is intentionally queued for post-Gate-2 `sdd-replan` Mode D (matching Phase 2 `9dceb09`).

---

## 2. The 5 Core Review Questions

| # | Question | Verdict | Evidence |
|:---|:---|:---|:---|
| 1 | Does it work, and is every requirement (`Feature 3.1` `R1`–`R10`, `Feature 3.2` `R1`–`R12`, NFRs, `INV-01`–`INV-09`, `P1`–`P8`) satisfied? | ✅ | Every functional requirement, NFR, constraint, and Phase 3 shared decision (`P1`–`P8`) traces bidirectionally across `feature-301/{requirements,validation}.md` and `feature-302/{requirements,validation}.md` and passes across `40` offline Vitest unit/integration/E2E tests and Tier 7 HTTP smoke against FastAPI (`163` backend tests green). |
| 2 | Is the diff free of unapproved scope, dead code, secrets, or sensitive-area edits (`git diff main..HEAD`)? | ✅ | `git diff --stat main..HEAD` touches only `44` `frontend/**` and `8` `spec/**` files (`0` `backend/**`, `0` Sensitive Areas, `0` `CHANGELOG.md`, `0` `sdd-profile.md`); `eslint src tests` and `tsc --noEmit` (`strict`, `noUncheckedIndexedAccess`) pass with `0` errors/warnings; zero secrets exist in `frontend/` and zero `next/font/google` imports exist (`INV-01`, `INV-07`). |
| 3 | Are all validation checks genuinely passing (offline frontend & backend suites, `ci`, `lint`, `typecheck`, offline `next build`, Tier 7 smoke)? | ✅ | Independent `@verifier` run (`#48`) on `f5e3ecc` passed: `npm.cmd --prefix frontend ci` (`465` added, `472` audited), `40 passed (40)` across `7` Vitest files (`13.11s`, `0` skipped/relaxed), `eslint src tests`, `tsc --noEmit`, offline `next build` (`Next.js 15.5.29`, `1946ms`), `uv run --no-sync --directory backend pytest -v` (`163 passed, 1 deselected, 1 warning in 66.73s`), `uv lock --check`, `ruff`, `mypy src`, and Tier 7 HTTP smoke (`200`/`413`/`404`/`503`). |
| 4 | Are `spec/` files in sync with the code? | ✅ | `feature-301/{plan,requirements,validation}.md`, `feature-302/{plan,requirements,validation}.md`, and `phase-overview.md` (`Committed`/`Validated`, `6731281` & `f5e3ecc` Execution Log entries, proxy hardening, search-oriented starter prompts, `canCompareSaved` `sessionId` gate, `sessionResetNonce`, and §5 evidence; Tier 6 `[ ]` preserved unchecked) are synced cleanly. `spec/sdd-profile.md` remains queued for Step 9 `sdd-replan` Mode D. |
| 5 | Are error handling, proxy hardening, grounding, and PII/XSS defenses clean? | ✅ | `proxy.ts` enforces JSON upstream responses (`502`/`>= 500` scrubbed + `nosniff`), `TRUST_PROXY_HEADERS`-gated `isIP`-validated `X-Forwarded-For`, `redirect: "error"`, `64 KiB` `413` cap, configurable `BACKEND_PROXY_TIMEOUT_MS` + `request.signal`, and sanitized `503 backend_unreachable`; `next.config.ts` emits anti-clickjacking/`nosniff` headers; `sanitizeHttpsUrl` blocks unsafe protocols/credentials; `formatExactPrice` preserves `DecimalString` precision; `storage.ts` validates nested shapes; `StatusBanner` & `ShoppingWorkspace` never echo/persist `refused` PII (`INV-01`, `INV-03`, `INV-05`, `INV-08`, `INV-09`). |

### Per-Feature Verdict Summary

| Scope Item | Spec Status | Verdict | Key Evidence (`#48` / `f5e3ecc`) |
|:---|:---|:---|:---|
| **Feature 3.1** — Arabic-First `RTL` App Shell, Selectors, Proxy & Typed API Client | `Committed` (`plan.md`, `requirements.md`), `Validated` (`validation.md`), `✅ Done` | ✅ Pass | `4` test files (`api.test.ts` `4`, `storage-and-format.test.ts` `4`, `proxy-routes.test.ts` `5`, `app-shell.test.tsx` `4` = `17/17` inside `40 passed`), `next.config.ts` headers, hardened `proxy.ts` & nested `storage.ts`, `eslint` / `tsc` / offline `next build` clean |
| **Feature 3.2** — Unified Dual-Mode Chat & Strictly Grounded Top-3 Comparison | `Committed` (`plan.md`, `requirements.md`), `Validated` (`validation.md`), `✅ Done` | ✅ Pass | `2` test files (`offer-card-and-banners.test.tsx` `7`, `shopping-workspace.test.tsx` `11` = `18/18` inside `40 passed`), unmount abort cleanup, `sessionId`-gated `canCompareSaved`, mixed AR/EN `dir="auto"` coverage |
| **Phase Integration (`PI.1`–`PI.3`)** & Deep Review Remediation | `Validated` (`phase-overview.md`) | ✅ Pass | `phase3-e2e.test.tsx` (`5/5` inside `40 passed`, `13.11s`), `163 passed` backend `pytest -v` (`66.73s`), `npm.cmd --prefix frontend ci`, offline `Next.js 15.5.29` build (`1946ms`), Tier 7 HTTP smoke `200`/`413`/`404`/`503` |

---

## 3. 4-Lens Deep Review Results & Finding Dispositions

Four parallel read-only review lenses audited `phase/3-rtl-web-experience` (`#41`–`#44`) prior to remediation commit `f5e3ecc`. All **0 High** and **8 Medium** findings—along with **13** actionable Low findings—were resolved in `f5e3ecc` and independently verified green by `@verifier` (`#48`), leaving **0 open High or Medium blockers**.

| Lens & Source | Finding | Severity | Disposition & Verification |
|:---|:---|:---|:---|
| **Lens 1: Security & Governance (`#41`)** | `forwardToBackend` (`proxy.ts:146-166`) copied non-JSON upstream bodies (`responseText`) and raw `content-type` verbatim without `nosniff`, risking host/trace leaks or `text/html` reflection (`INV-01`/`INV-08`). | **Medium** | **Fixed in `f5e3ecc`** (verified `#48`): required upstream `application/json` or `+json` AND `JSON.parse(responseText)` success; replaced invalid/non-JSON responses with sanitized `jsonErrorResponse` (`502 upstream_invalid_response` or `>= 500 backend_unreachable`), always emitting `Content-Type: application/json; charset=utf-8` and `X-Content-Type-Options: nosniff`. |
| **Lens 1 (`#41`)** | `forwardToBackend` (`proxy.ts:112-115`) unconditionally forwarded client `X-Forwarded-For` over loopback to FastAPI (`trusted_proxy_cidrs` includes `127.0.0.1`), enabling rate-limit rotation bypass. | **Medium** | **Fixed in `f5e3ecc`** (verified `#48`): gated `X-Forwarded-For` forwarding behind `process.env.TRUST_PROXY_HEADERS === "true"` (`TRUST_PROXY_HEADERS=false` documented in `frontend/.env.example`), validated every comma-separated IPv4/IPv6 hop with Node `node:net` `isIP(hop) !== 0`. |
| **Lens 1 (`#41`)** & **Lens 2 (`#43`)** | `sanitizeActiveComparison` & `sanitizeMessages` (`storage.ts:89-91, 100-135`) validated only top-level `rankedOffers` array / `rankingResult` / `telemetry` records without nested element/field validation. | **Medium** (`#43`) / **Low** (`#41`) | **Fixed in `f5e3ecc`** (verified `#48`): added strict `sanitizeProductOffer`, `sanitizeRankedOffer`, `sanitizeRankingResult`, and `sanitizeTurnTelemetry` helpers returning `null` / omitting corrupted entries cleanly instead of crashing `OfferCard` or `TelemetryStrip`. |
| **Lens 1 (`#41`)** | Upstream `fetch` (`proxy.ts:124, 129-135`) omitted `redirect: "error"` and buffered unbounded `request.text()` on `POST`. | **Low** | **Fixed in `f5e3ecc`** (verified `#48`): set `redirect: "error"` (mapped to `503 backend_unreachable`) and capped `POST` request bodies at `64 KiB` (`65536` UTF-8 bytes), returning HTTP `413` `ErrorResponse(error_code="payload_too_large", retriable=false)` with `0` upstream `fetch` calls. |
| **Lens 1 (`#41`)** | `next.config.ts` & `proxy.ts` omitted browser defense-in-depth headers. | **Low** | **Fixed in `f5e3ecc`** (verified `#48`): added `headers()` in `frontend/next.config.ts` (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Content-Security-Policy: frame-ancestors 'none'`) and `X-Content-Type-Options: nosniff` on all proxy responses. |
| **Lens 2: Architecture, Scalability & Cost (`#43`)** | Four `STARTER_PROMPTS` queries (`i18n.ts:34,57,63-64`) started with `"Compare..."`/`"مقارنة..."`, triggering backend rule-fallback `_COMPARE_PATTERNS` (`TurnAction.COMPARE`) on fresh sessions (`0` offers `CLARIFY`). | **Medium** | **Fixed in `f5e3ecc`** (verified `#48` + Tier 7 `SA` EN/AR `action=search`): rephrased `eg-air-fryer` EN, `sa-air-fryer` EN, and `sa-iphone-15` AR/EN queries to search-oriented phrasing and added regex regression assertions in `storage-and-format.test.ts`. |
| **Lens 2 (`#43`)** | `V1_TIMEOUT_MS = 12_000` (`proxy.ts:7,134`) was hardcoded and omitted `request.signal` cancellation forwarding. | **Low** | **Fixed in `f5e3ecc`** (verified `#48`): added optional `BACKEND_PROXY_TIMEOUT_MS` (default `12000`, clamped `1000..60000`, documented in `.env.example`) and combined `AbortSignal.timeout(timeoutMs)` with `request.signal` via `AbortSignal.any` and listener fallback. |
| **Lens 2 (`#43`)** | `ShoppingWorkspace.tsx:127-137` `[country, sessionResetNonce]` effect omitted an unmount `AbortController` cleanup return. | **Low** | **Fixed in `f5e3ecc`** (verified `#48`): returned `() => { if (inFlightControllerRef.current) { inFlightControllerRef.current.abort(); inFlightControllerRef.current = null; } }` cleanup. |
| **Lens 2 (`#43`)** | `ShopSessionContext.tsx` called `saveMarketSessions` inside `setMarketSessions` updaters, lacked a request-sequence/`AbortController` guard on overlapping `refreshHealth()` calls, and did not retry `refreshMarkets()` from `HealthBadge` when `marketsError` was `true`. | **Low** | **Partially fixed in `f5e3ecc` & remainder accepted/deferred**: made `setMarketSessions` updaters pure with post-hydration `useEffect` persistence (`sessionsHydrated`) and added `healthRequestSeqRef` + `healthAbortControllerRef` guard on overlapping `refreshHealth()` calls (verified `#48`); kept `refreshHealth()` decoupled from `refreshMarkets()` (`#45`) so health polling never unexpectedly fires extra `/api/v1/markets` traffic (manual market retry can be added in Phase 4 UX if desired). |
| **Lens 2 (`#43`)** | `ShoppingWorkspace.tsx:532` enabled `canCompareSaved` after Direct Search when `activeMarketSession.sessionId === null`. | **Low** | **Fixed in `f5e3ecc`** (verified `#48`): gated `canCompareSaved` on `activeMarketSession.sessionId !== null && activeOffers.length >= 2`, keeping `COMPARE` consistent with backend session state and syncing `feature-302` & `phase-overview.md`. |
| **Lens 3: Spec Drift & Governance (`#44`)** | `phase-overview.md:6,215` stayed `Status: Implementing` with `— (pending verification & commit)` despite `6731281`. | **Low** | **Fixed in `f5e3ecc` & Gate 2 finalization**: recorded `6731281` & `f5e3ecc` in `phase-overview.md` §7 Execution Log and advanced `- **Status**: Validated`. |
| **Lens 3 (`#44`)** | Stale `> Status: Draft (Pending Phase Gate 1 Approval)` in `feature-301/{requirements,validation}.md` and `feature-302/{requirements,validation}.md`. | **Low** | **Fixed in `f5e3ecc`** (verified `#48`): updated `requirements.md` headers to `Committed` and `validation.md` headers to `Validated` (plus proxy/storage/session/starter spec sync). |
| **Lens 3 (`#44`)** | `spec/sdd-profile.md:10,16-18` retains `(unverified — greenfield target, Feature 3.1)` tags on frontend scripts and omits `npm --prefix frontend test` / `start`. | **Low** | **Queued for post-Gate-2 `sdd-replan` Mode D**: constitution files (`spec/sdd-profile.md`) are intentionally untouched during Gate 2 review per `sdd-conventions` §0/§4. |
| **Lens 3 (`#44`)** | `sessionResetNonce: number` on `ShopSessionContextValue` (`ShopSessionContext.tsx:112`) was omitted from `phase-overview.md:149` and `feature-301/plan.md:173`. | **Low** | **Fixed in `f5e3ecc`** (verified `#48`): documented `sessionResetNonce: number` in both `feature-301/plan.md` and `phase-overview.md`. |
| **Lens 4: Test & Eval Quality (`#42`)** | `proxy-routes.test.ts:198-208,284-304` omitted `X-Request-ID` on `503` outage tests, risking ~1-in-4,096 UUIDv4 collisions against `"9123"`/`"8000"`. | **Medium** | **Fixed in `f5e3ecc`** (verified `#48`): passed deterministic `X-Request-ID` headers, verified echo, and asserted scrubbing on parsed JSON fields (`message`, `error_code`, `details`). |
| **Lens 4 (`#42`)** | `shopping-workspace.test.tsx` `T3.2` omitted `signal.aborted`, abort-rejection handling, `sendingButton` disabled check, switching back to `EG`, and Direct Search race cancellation. | **Medium** | **Fixed in `f5e3ecc`** (verified `#48`): verified `AbortSignal.aborted === true`, abort rejection handling without false error banners, disabled `sendingButton`, clean origin market after switch-back, and equivalent `searchOffers` race test. |
| **Lens 4 (`#42`)** | Zero mixed Arabic/English query round-trips or `dir="auto"` assertions on `OfferCard`, `ChatThread`, or `MessageComposer`. | **Medium** | **Fixed in `f5e3ecc`** (verified `#48`): added `dir="auto"` assertions across `offer-card-and-banners.test.tsx`, `shopping-workspace.test.tsx`, and a mixed Arabic/English round-trip in `phase3-e2e.test.tsx`. |
| **Lens 4 (`#42`)** | `proxy-routes.test.ts` omitted `POST` `body`, `Content-Type`, `cache: "no-store"`, `signal`, malformed `X-Request-ID`, `X-Request-ID` echo on `404`/`405`/`503`, `path: []`, `PATCH`, `/api/health` `PUT`/`PATCH`/`DELETE`, and invalid `BACKEND_API_URL` scheme -> `503`. | **Medium** | **Fixed in `f5e3ecc`** (verified `#48`): added complete assertions and coverage across all proxy routes, methods, hardening rules (`413`, `502`, `TRUST_PROXY_HEADERS` + `isIP`, `redirect: "error"`, `BACKEND_PROXY_TIMEOUT_MS`), and `AbortSignal.any` fallback. |
| **Lens 4 (`#42`)** | `shopping-workspace.test.tsx` `T2.2` (`0` LLM calls + thread preservation), `T3.3` (`refused` composer clear, `degraded` Retry, `generic_error`), `T3.5` (Direct Search `503` + Retry), `api.test.ts` (`AbortSignal` + `200` `invalid_json`), `storage-and-format.test.ts` (malformed `formatExactPrice` + `rankedOffers: [null]`), `app-shell.test.tsx` (`degraded` health), `Shift+Enter`, and centralized `tests/setup.ts` cleanup. | **Low** (4 items) | **Fixed in `f5e3ecc`** (verified `#48`): added all missing unit/integration assertions across `tests/setup.ts`, `api.test.ts`, `storage-and-format.test.ts`, `app-shell.test.tsx`, and `shopping-workspace.test.tsx`. |

---

## 4. Exact Validation Evidence (`#48` Independent Verifier Run on `f5e3ecc`)

All automated checks below were independently executed by `@verifier` (`#48`) against the committed `f5e3ecc` state (100% offline deterministic except the local non-interactive Tier 7 `127.0.0.1` smoke):

| Gate | Command | Observed Output | Status |
|:---|:---|:---|:---|
| **Lockfile Reproducibility (`PI.2`)** | `npm.cmd --prefix frontend ci` | `added 465 packages, and audited 472 packages in 3m` (exit `0`) | ✅ |
| **Full Offline Frontend Suite (`PI.2`, `INV-07`)** | `npm.cmd --prefix frontend test -- --reporter=verbose` | `Test Files 7 passed (7)`, `Tests 40 passed (40)` in `13.11s` (`api.test.ts` `4`, `storage-and-format.test.ts` `4`, `proxy-routes.test.ts` `5`, `offer-card-and-banners.test.tsx` `7`, `app-shell.test.tsx` `4`, `shopping-workspace.test.tsx` `11`, `phase3-e2e.test.tsx` `5`; `0` skipped, `0` failed) | ✅ |
| **Frontend Lint (`PI.3`)** | `npm.cmd --prefix frontend run lint` (`eslint src tests`) | Exit `0` (`0` errors, `0` warnings) | ✅ |
| **Frontend Typecheck (`PI.3`)** | `npm.cmd --prefix frontend run typecheck` (`tsc --noEmit`) | Exit `0` (`strict: true`, `noUncheckedIndexedAccess: true`) | ✅ |
| **Offline Production Build (`PI.3`, `INV-07`)** | `npm.cmd --prefix frontend run build` (`next build`) | `Next.js 15.5.29` `Compiled successfully in 1946ms` (exit `0`; `/` `9.03 kB` / `123 kB` First Load JS, `/_not-found` `993 B`, `/api/health` `127 B`, `/api/v1/[...path]` `127 B`; `0` `next/font/google` hits) | ✅ |
| **Full Offline Backend Regression (`PI.2`)** | `uv run --no-sync --directory backend pytest -v` | `163 passed, 1 deselected, 1 warning in 66.73s` (`@pytest.mark.live` deselected; `0` `backend/**` edits), plus `uv lock --check` (`70 packages`), `ruff check .`, `ruff format --check .` (`62 files`), `mypy src` (`43 source files`) | ✅ |
| **Tier 7 Full-Stack HTTP Smoke (`T7.1`)** | FastAPI (`CATALOG_MODE=seed`, `LLM_MODE=fake` on `:8000`) + Next.js (`BACKEND_API_URL=http://127.0.0.1:8000`, `npm.cmd --prefix frontend run start -- --port 3000`) | `GET /` `200` (`rtl: true`, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `CSP: frame-ancestors 'none'`); `GET /api/health` `200` (`Content-Type: application/json; charset=utf-8`, `nosniff`); `GET /api/v1/markets` `200` (`EG,SA,AE`); `POST /api/v1/search` `200` (`source=seed`, `degraded=true`, `offers=2`, `top1=6799.00`); `POST /api/v1/chat` (`EG` AR + `SA` iPhone 15 AR/EN starter prompts) `200` (`status=ok`, `action=search`, `offers=3`); `POST /api/v1/chat` (`>64KiB`) `413` (`nosniff`, `payload_too_large`); `GET /api/v1/unknown` `404` (`nosniff`, `route_not_found`); FastAPI stopped → `GET /api/health` `503` (`nosniff`, `backend_unreachable`, `retriable=true`, `0` URL leak); `PORTS_8000_3000_FREE` | ✅ |
| **Extra Gates (`PI.4`: `tests/evals`)** | `uv run --directory backend pytest tests/evals -v` | **Not Applicable** — `spec/sdd-profile.md` makes `backend/tests/evals/` mandatory from **Feature 4.1** onward | ⏭ N/A |
| **Tier 6 (`T6.1`–`T6.2`: Live Browser RTL/LTR & Responsive)** | Manual visual inspection in browser (`1280x800` & `375x812`) | **Pending Human Sign-Off at Gate 2** — left unchecked `[ ]` in `feature-301/validation.md` & `feature-302/validation.md` | Pending |

### Manual Gate 2 Browser Launch & Inspection Commands

```powershell
# 1. Prepend Node.js LTS to PATH in PowerShell and start FastAPI backend on :8000 (Terminal 1)
$env:DATABASE_URL = "sqlite+aiosqlite:///" + (($env:TEMP -replace "\\", "/") + "/phase3_gate2_manual.db")
$env:CATALOG_MODE = "seed"
$env:LLM_MODE = "fake"
uv run --no-sync --directory backend uvicorn commerce_ai.main:app --port 8000

# 2. Start Next.js frontend dev server on :3000 (Terminal 2)
$env:Path = "$env:LOCALAPPDATA\Programs\nodejs;" + $env:Path
$env:BACKEND_API_URL = "http://127.0.0.1:8000"
npm.cmd --prefix frontend run dev
```

**Manual Browser Walkthrough Checklist (`http://localhost:3000`)**:
1. **Desktop `1280x800` (`RTL` Arabic default — `T6.1`)**: Verify `<html lang="ar" dir="rtl">`, crisp native Arabic typography, `MarketSelector` (`مصر`/`السعودية`/`الإمارات`), `StoreFilterBar`, `BudgetCapControl` currency label + inline invalid-budget feedback (`-50`), `HealthBadge` (`متصل`), and `ModeToggle`.
2. **Chat, Starter Prompts & Compare (`T6.1`)**: Click an `EG` / `SA` starter prompt (verifying search classification & Top-3 grounded `OfferCard` badges, prices, Bayesian rating / Unrated badge, `value_score` bar, localized `match_reasons`, `TelemetryStrip`, and `rel="noopener noreferrer"` store CTA), then click **"قارن أفضل العروض"**.
3. **Zero-LLM Direct Search & Instant `ar` ↔ `en` Toggle (`T6.1`)**: Switch to **بحث مباشر (بدون LLM)**, query `"air fryer"` with `min_rating=4.5` & `include_accessories`, verify `0` LLM calls in `TelemetryStrip`, then toggle `LanguageToggle` to **English (`LTR`)** without reload and verify layout parity.
4. **Mobile `375x812` (`RTL` & `LTR` — `T6.2`)**: Confirm `document.documentElement.scrollWidth <= window.innerWidth` (zero horizontal overflow), visible quick-jump link to `#comparison-panel`, clean wrapping on mixed Arabic/English offer titles, and legible `StatusBanner` readability.

---

## 5. Phase Gate 2 Recommendation & Post-Approval Actions

- **Verdict / Status**: **`APPROVED`** (Phase Gate 2 approved by human on 2026-11-17)
- **Recommendation**: Phase 3 (`phase/3-rtl-web-experience`) passes all `40` offline unit/integration/E2E tests, `eslint`, strict `tsc`, offline `Next.js 15.5.29` build, `163` backend regression tests, Tier 7 full-stack HTTP verification, architectural invariants (`INV-01`–`INV-09`), and 4-lens deep review with **0 open High or Medium blockers**, and is ready for **🛑 Phase Gate 2** human visual inspection (`T6.1`–`T6.2`) and approval.
- **Post-Approval Actions (execute ONLY after human approval at Gate 2)**:
  1. Update `phase-review.md` status (`APPROVED`) and commit Gate 2 review docs (`phase-review.md`, `phase-overview.md`).
  2. Run `sdd-changelog` to append Phase 3 stakeholder release notes (`Feature 3.1` & `Feature 3.2`) to `CHANGELOG.md` and commit.
  3. Push branch (`git push -u origin phase/3-rtl-web-experience`) and merge into `main` via `git merge --no-ff` (per `spec/sdd-profile.md`), updating `phase-overview.md` Status to `Merged`.
  4. Run `sdd-replan` Mode D for Phase 3 closeout on a `replan/` branch: record Phase 3 retrospective notes, mark verified frontend commands (`ci`, `lint`, `typecheck`, `build`, `dev`) and add `npm --prefix frontend test` / `start` in `spec/sdd-profile.md`, and verify Phase 4 readiness.
