# Technical Specification & Invariants — AI for E-Commerce

> Status: Draft (Pending Human Constitution Approval)
> Legend: `(verified in env)` = checked in workspace VM; `(confirmed target)` = agreed greenfield stack choice.

## 1. Technology Stack

| Layer | Technology | Version | Role & Rationale |
|:---|:---|:---|:---|
| Backend Language | Python | `3.11+` (`3.11.2` verified in env) | Primary enterprise AI & data ecosystem language |
| Python Package Manager | `uv` | `0.13+` (`0.13.7` verified in env) | Fast, deterministic lockfile & virtualenv management |
| Backend API | `FastAPI` + `Pydantic v2` + `Uvicorn` | Latest stable `(confirmed target)` | Async HTTP/SSE API, strict request/response validation, OpenAPI 3.1 generation |
| Agent Orchestration | `LangGraph` | Latest stable `(confirmed target)` | Bounded, stateful workflow graph with deterministic edges and session checkpointing |
| LLM Routing Layer | Typed `LLMProvider` (`LiteLLM` / native async SDKs) | Latest stable `(confirmed target)` | Model routing across low-cost providers (`Gemini 2.5 Flash`, `Groq`, `OpenAI mini`, `AWS Bedrock Haiku/Nova`) + offline `FakeLLMProvider` |
| Marketplace Search | `httpx` + `Serper.dev` Shopping/Search API + `SeedCatalogProvider` | Async HTTP `(confirmed target)` | Fast sub-second Noon & Amazon (`EG`/`SA`/`AE`) offer retrieval without fragile scraping, paired with deterministic local seed data |
| Primary Database | `PostgreSQL` (`SQLAlchemy 2.0` async + `Alembic`) + `SQLite` (`aiosqlite`) | PG `16` `(confirmed target)` | Session state, query audit logs, and future B2B catalog/tenant configs; `SQLite` fallback for zero-setup local dev & CI |
| Caching Layer | `Redis` + In-Memory `TTLCache` | Redis `7` `(confirmed target)` | Exact & normalized-intent caching to cut external API/LLM costs and achieve `< 300 ms` repeat responses |
| Frontend Web App | `Next.js` (App Router) + `React` + `TypeScript` + `Tailwind CSS` | Node `24 LTS` (`24.22.2` verified in env) | Lightweight Arabic-first (`RTL`) chat & 3-card product comparison interface, decoupled via REST/SSE |
| LLMOps & Observability | `Langfuse` + `structlog` | Open-source / Cloud free tier `(confirmed target)` | End-to-end trace logging, token/cost accounting, latency P95 tracking, and graceful no-op when unconfigured |
| Quality & Testing | `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `eslint`, `tsc` | Latest stable `(confirmed target)` | Unit, contract, integration, golden-dataset AI evals, linting, and static type safety |
| Containers & Cloud | `Docker` (multi-stage), `Docker Compose`, `GitHub Actions`, `AWS ECR`, `AWS App Runner` / `ECS Fargate` | Serverless containers `(confirmed target)` | Low-cost AWS production with zero idle Kubernetes control-plane fees and 100% portability to enterprise on-premise servers |

---

## 2. Non-Negotiable Architectural Invariants

Every feature specification, code change, and review MUST uphold these numbered invariants:

1. **INV-01 — Zero Hardcoded Secrets**: API keys, database URLs, and credentials MUST NEVER appear in source files, tests, specs, logs, or container layers. All configuration loads through typed `pydantic-settings` from `.env` (local, git-ignored) or `AWS Secrets Manager` (production).
2. **INV-02 — Strict Ports & Adapters (Hexagonal Boundary)**: Domain models (`domain/`), ranking math (`domain/ranking.py`), and workflow nodes (`agent/`) MUST depend exclusively on abstract interfaces/protocols (`CatalogProvider`, `LLMClient`, `CacheStore`, `SessionRepository`). Vendor-specific HTTP calls or SDK imports (`serper`, `redis`, `langfuse`, `boto3`, etc.) are restricted to `adapters/`.
3. **INV-03 — Deterministic Math & Configurable Scoring**: Price normalization, currency alignment, accessory exclusion, and Top-3 value scoring (combining price and Bayesian-weighted rating) MUST run in pure, deterministic Python—never delegated to LLM free-text reasoning. Scoring weights (`price_weight`, `rating_weight`, `bayesian_prior_count`, `bayesian_prior_mean`) MUST live in typed configuration so they can be tuned per market or B2B tenant without code edits.
4. **INV-04 — Bounded Agent Execution & Cost Ceiling**: The `LangGraph` workflow MUST NOT use unbounded autonomous loops. Every user turn executes a fixed upper bound of **at most 2 LLM calls** (1 structured intent extraction call + at most 1 concise Arabic/English summary or clarification call) with explicit `max_tokens` limits and HTTP timeouts.
5. **INV-05 — Zero Hallucinated Offers (Strict Grounding)**: The assistant MUST NEVER invent, modify, or extrapolate product titles, prices, currencies, star ratings, review counts, store names, or purchase URLs. Every field on the Top-3 cards MUST originate directly from a verified `CatalogProvider` item.
6. **INV-06 — Sanctioned Data Acquisition Only**: Headless browser scraping, anti-bot circumvention, and CAPTCHA solving against Noon, Amazon, or any marketplace are strictly prohibited. Live marketplace queries use official/commercial Search/Shopping APIs or merchant-provided data feeds.
7. **INV-07 — 100% Offline Deterministic Test Suite**: Standard unit and integration test suites (`uv run pytest`) MUST execute completely offline in `< 30 s` using `SeedCatalogProvider`, `FakeLLMClient`, in-memory cache, and `SQLite`, requiring zero paid API keys in CI. Live external API checks are isolated behind explicit opt-in integration markers (`@pytest.mark.live`).
8. **INV-08 — Graceful Degradation**: If an external LLM or Search API times out, errors, or returns fewer than 3 qualifying products, the system MUST degrade gracefully—using rule-based fallback parsing/formatting where possible and returning verified partial matches (`0–2` items) with a structured status banner rather than HTTP 500 crashes or fabricated items.
9. **INV-09 — Zero Payment or Sensitive PII Scope**: MVP APIs, logs, and storage MUST NOT accept, store, or transmit payment card details, passwords, or government IDs. Outbound store links open safely with `rel="noopener noreferrer"`.

---

## 3. Repository & Folder Conventions

```text
/
├── backend/
│   ├── pyproject.toml                  # Dependencies, ruff, mypy, pytest config
│   ├── .env.example                    # Documented variable names only (no secrets)
│   ├── src/
│   │   └── commerce_ai/
│   │       ├── main.py                 # FastAPI app factory & lifespan hooks
│   │       ├── config/                 # pydantic-settings, country/store registry, scoring profiles
│   │       ├── domain/                 # Pure Pydantic/dataclass entities, ports (protocols), deterministic ranking
│   │       ├── agent/                  # LangGraph state, nodes, model router policy, prompt templates, guardrails
│   │       ├── adapters/
│   │       │   ├── catalog/            # SeedCatalogProvider, SerperShoppingProvider, Composite/Cached provider
│   │       │   ├── llm/                # LiteLLM / multi-provider client + FakeLLMClient
│   │       │   ├── cache/              # RedisCacheStore + InMemoryTTLCache
│   │       │   ├── session/            # SQLAlchemy (Postgres/SQLite) + InMemorySessionStore
│   │       │   └── observability/      # Langfuse tracer + structured logger
│   │       └── api/                    # Versioned FastAPI routers (/api/v1/...), schemas, error handlers
│   └── tests/
│       ├── unit/                       # Ranking math, filters, config, guardrails
│       ├── integration/                # FastAPI endpoints, LangGraph flows, cache/session persistence
│       └── evals/                      # Golden Arabic/English queries & Top-3 relevance assertions
├── frontend/
│   ├── package.json
│   ├── next.config.ts
│   └── src/
│       ├── app/                        # Next.js App Router (RTL default layout, Arabic typography)
│       ├── components/                 # ChatThread, MessageComposer, ProductComparisonGrid, OfferCard, MarketSelector
│       └── lib/                        # Typed API client & formatting utilities
├── infra/
│   ├── docker/                         # Multi-stage backend.Dockerfile & frontend.Dockerfile
│   └── aws/                            # App Runner / ECS Fargate task definitions & deployment runbook
├── docker-compose.yml                  # Local full-stack orchestration (backend, frontend, postgres, redis)
├── .github/workflows/ci.yml            # Automated lint, type-check, test, and eval gate
└── spec/                               # SDD single source of truth
```

---

## 4. Testing & Evaluation Strategy

1. **Unit Tests (`backend/tests/unit/`)**: Edge-case coverage for Bayesian rating math (e.g., `5.0` with `1` review vs. `4.7` with `900` reviews), accessory keyword & price-floor outlier rejection, currency/country mapping (`EG`->`EGP`, `SA`->`SAR`, `AE`->`AED`), and prompt-injection input sanitization.
2. **Integration & Contract Tests (`backend/tests/integration/`)**: End-to-end FastAPI request/response validation (`httpx.AsyncClient`), multi-turn session refinement in `LangGraph`, cache hit/miss behavior, and provider timeout degradation.
3. **AI Evaluation Suite (`backend/tests/evals/`)**: Curated golden benchmark of Egyptian/Gulf Arabic and English shopping queries paired with seeded marketplace catalogs verifying:
   - Intent accuracy (product, store filter, budget cap, country).
   - Anti-accessory precision (no cases/chargers returned when searching for a core device).
   - Zero price/URL hallucination.
4. **Frontend Checks (`frontend/`)**: TypeScript strict compilation (`npm run typecheck`), ESLint (`npm run lint`), and production build verification (`npm run build`).

---

## 5. Deployment Topology (MVP -> Scale)

- **Local Development**: Single command via `uv run uvicorn ...` + `npm run dev` (using `SQLite` + in-memory cache + `SeedCatalogProvider` out of the box), or full parity via `docker compose up --build` (`PostgreSQL` + `Redis`).
- **AWS Production (Low-Cost MVP)**:
  - Container images built via `GitHub Actions` and pushed to `AWS ECR`.
  - Backend and Frontend deployed on **`AWS App Runner`** or **`AWS ECS Fargate`** in a close low-latency region (e.g., `me-central-1` UAE, `me-south-1` Bahrain, or `eu-central-1` Frankfurt).
  - Secrets injected at runtime from `AWS Secrets Manager`.
  - Managed `RDS PostgreSQL` (micro/serverless) and `ElastiCache Redis` (or Upstash serverless Redis for near-zero MVP fixed cost).
- **Enterprise On-Premise Portability**: Because zero business logic depends on proprietary AWS SDKs, the exact same Docker containers deploy cleanly onto any enterprise client's private Kubernetes (`Rancher` / `kubeadm`) or Linux VM environment alongside local LLMs (`vLLM` / `Ollama`).
