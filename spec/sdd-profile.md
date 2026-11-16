# SDD Project Profile — AI for E-Commerce

> Project-specific settings read by every `sdd-*` skill. Part of the constitution: change it via `sdd-replan`.
> Values marked `(discovered)` were inferred from the repo/environment; values marked `(confirmed)` were confirmed by the human; commands marked `(unverified — greenfield target)` will be initialized and verified when their scaffolding feature lands.

## Commands
| Purpose | Command |
|:---|:---|
| Install / sync deps (backend) | `uv sync --directory backend --all-extras --dev` `(confirmed — verified Feature 1.1 T5.1)`; lock check: `uv lock --directory backend --check` `(confirmed — verified Phases 1–2)` |
| Install / sync deps (frontend) | `npm --prefix frontend ci` `(unverified — greenfield target, Feature 3.1)` |
| Full test suite (backend) | `uv run --directory backend pytest -v` `(confirmed — verified Phases 1–2; --no-sync variant used in validation runs)` |
| Targeted tests (backend) | `uv run --directory backend pytest <file> -v` `(confirmed — verified Phases 1–2; --no-sync variant used in validation runs)` |
| Lint (backend) | `uv run --directory backend ruff check .` `(confirmed — verified Phases 1–2; --no-sync variant used in validation runs)` |
| Format check (backend) | `uv run --directory backend ruff format --check .` `(confirmed — verified Phases 1–2; --no-sync variant used in validation runs)` |
| Type check (backend) | `uv run --directory backend mypy src` `(confirmed — verified Phases 1–2; --no-sync variant used in validation runs)` |
| Lint & Type check (frontend) | `npm --prefix frontend run lint && npm --prefix frontend run typecheck` `(unverified — greenfield target, Feature 3.1)` |
| Build (frontend) | `npm --prefix frontend run build` `(unverified — greenfield target, Feature 3.1)` |
| Run app (manual checks) | Backend: `uv run --directory backend uvicorn commerce_ai.main:app --reload --port 8000` `(confirmed — ASGI smoke T7.1, Phase 2)`; `npm --prefix frontend run dev` `(unverified — greenfield target, Feature 3.1)`; `docker compose up --build` `(unverified — greenfield target, Feature 4.2)` |
| Extra gates (evals, e2e, security scans) | `uv run --directory backend pytest tests/evals -v` (mandatory from Feature 4.1 onward) `(unverified — greenfield target)` |

## Main Branch & Remote
- Main branch: `main` `(discovered)`
- Remote: `https://github.com/MaahmoudAbdelghany/AI-for-E-Commerce..git` `(discovered)`
- Merge style: `merge --no-ff` (or PR when requested by human) `(confirmed)`

## Execution Mode
- Default: `phase` `(confirmed)`

## Sensitive Areas (force feature mode + mandatory deep review)
- Cloud IAM, deployment secrets, and CI/CD pipelines (`infra/aws/**`, `.github/workflows/**`) `(confirmed)`
- Security boundaries, prompt-injection guardrails, and any future tenant authentication or database migrations (`backend/src/commerce_ai/config/security*`, `backend/migrations/**`) `(confirmed)`

## Deep Review Lenses
Four parallel read-only subagents:
1. `Security & Governance (OWASP Top 10 for LLMs, prompt injection, secret leakage, INV-01 & INV-09)`
2. `Architecture, Scalability & Cost Control (Hexagonal boundaries INV-02, deterministic math INV-03, <= 2 LLM calls INV-04, zero hallucination INV-05)`
3. `Spec Drift (requirements <-> validation <-> code <-> roadmap <-> OpenAPI contracts)`
4. `Test & Eval Quality (100% offline determinism INV-07, Arabic/English edge cases, accessory/Bayesian-rating traps, zero fabricated assertions)`

## Key Invariants to Check in Review
- `INV-01`: Zero hardcoded API keys or secrets anywhere; everything via `pydantic-settings` / env / Secrets Manager.
- `INV-02`: Core domain & agent modules depend only on abstract protocols (`CatalogProvider`, `LLMClient`, `CacheStore`, `SessionRepository`).
- `INV-03`: Top-3 ranking, Bayesian rating weighting, and accessory filtering execute in deterministic Python with configurable weights—never delegated to LLM arithmetic.
- `INV-04`: Bounded `LangGraph` flow (`<= 2` LLM calls per turn, lightweight routed models by default).
- `INV-05`: Strict grounding—zero hallucinated product prices, ratings, review counts, or store URLs.
- `INV-07`: `pytest` passes 100% offline without external API keys.

## Feature Folder Pattern
- `spec/features/feature-<phase><nn>-<slug>/` `(confirmed)`

## Language
- Artifact language (specs, code, commits, changelog): `English` `(confirmed)`
- Conversation language (messages to the human): `Arabic (RTL, wrapped in <div dir="rtl"> ... </div>)` `(confirmed)`
- Approval words: `approved, go ahead, proceed, موافق, اعتمد, نفذ, تمام نفذ, اعتمد الخطة` `(confirmed)`

## Changelog
- File: `CHANGELOG.md` · Audience: `Product owners, enterprise stakeholders, and developers` · Title line: `AI for E-Commerce — Changelog`
