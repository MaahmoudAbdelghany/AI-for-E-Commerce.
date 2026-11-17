# Project Roadmap — AI for E-Commerce

> **Living Document**: Managed through Spec-Driven Development (`sdd-phase`, `sdd-feature-spec`, and `sdd-replan`).
> Strategy: Ship a lean, low-cost, production-grade **MVP** across 4 small phases before expanding into B2B connectors and messaging channels.

---

## Phase 1 — Core Foundation, Deterministic Ranking & Pluggable Catalog Layer
**Goal**: Establish a clean Python backend foundation, typed regional marketplace schemas (`EG`/`SA`/`AE`), the configurable deterministic Top-3 Value Scoring engine, and pluggable catalog/cache adapters that work both offline (`SeedCatalogProvider`) and live (`SerperShoppingProvider`).

- [x] **Feature 1.1**: Backend scaffold, `pydantic-settings` config, and regional marketplace domain models (`backend/pyproject.toml`, `backend/src/commerce_ai/config/`, `backend/src/commerce_ai/domain/models.py`)
- [x] **Feature 1.2**: Deterministic Top-3 Value Scoring engine (normalized price + Bayesian rating) and anti-accessory/outlier filter (`backend/src/commerce_ai/domain/ranking.py`, `backend/tests/unit/test_ranking.py`)
- [x] **Feature 1.3**: Pluggable `CatalogProvider` & `CacheStore` interfaces, `SeedCatalogProvider` (`Noon` & `Amazon` fixtures for `EG`/`SA`/`AE`), `SerperShoppingProvider`, and TTL caching (`backend/src/commerce_ai/adapters/catalog/`, `backend/src/commerce_ai/adapters/cache/`)

---

## Phase 2 — Bounded LangGraph Shopping Agent, Model Routing & FastAPI Service
**Goal**: Connect natural-language Arabic/English shopping queries to the deterministic ranking engine via an economical, bounded `LangGraph` workflow with session memory, graceful degradation, and documented `FastAPI` endpoints.

- [x] **Feature 2.1**: Pluggable `LLMClient` with economical model routing, input guardrails, Arabic/English structured intent extraction, and folded [Phase 1 cache/settings follow-ups](backlog/2026-11-15-phase1-cache-and-settings-followups.md) (`@field_serializer` URL redaction in `AppSettings`, `SearchIntent` Arabic folding & `catalog_cache_key()`, single-flight `CachedCatalogProvider`) (`backend/src/commerce_ai/adapters/llm/`, `backend/src/commerce_ai/agent/intent.py`, `backend/src/commerce_ai/agent/guardrails.py`, `backend/src/commerce_ai/config/settings.py`, `backend/src/commerce_ai/domain/models.py`, `backend/src/commerce_ai/adapters/catalog/cached_provider.py`)
- [x] **Feature 2.2**: Bounded `LangGraph` shopping assistant workflow (`parse -> clarify_or_fetch -> rank -> explain`) with `SQLite`/`PostgreSQL` session memory and fallback handling (`backend/src/commerce_ai/agent/graph.py`, `backend/src/commerce_ai/adapters/session/`)
- [x] **Feature 2.3**: Versioned `FastAPI` service (`/api/v1/chat`, `/api/v1/search`, `/api/v1/markets`, `/health`), structured error responses, and integration tests (`backend/src/commerce_ai/api/`, `backend/src/commerce_ai/main.py`, `backend/tests/integration/`)

---

## Phase 3 — Arabic-First (`RTL`) Next.js Web Experience
**Goal**: Deliver a clean, responsive Arabic/English web interface where shoppers and enterprise stakeholders can converse with the assistant, switch countries/stores, and compare the Top 3 best-value products side by side.

- [x] **Feature 3.1**: `Next.js` TypeScript + Tailwind `RTL` application shell, market selector (`Egypt EGP`, `Saudi SAR`, `UAE AED`), store filter (`All`, `Noon`, `Amazon`), and typed API client (`frontend/package.json`, `frontend/src/app/`, `frontend/src/lib/api.ts`)
- [ ] **Feature 3.2**: Interactive shopping chat experience, Top-3 comparison card grid (price, Bayesian rating badge, review count, value-score reason, direct store CTA), and degradation/empty states (`frontend/src/components/`)

---

## Phase 4 — LLMOps Observability, Evaluation Gate, Containers & AWS Deployment
**Goal**: Instrument token cost and latency tracing, prove ranking and Arabic intent quality via an automated evaluation suite, and package the stack for low-cost AWS container deployment.

- [ ] **Feature 4.1**: `Langfuse` trace & token-cost integration, structured JSON logging, and golden-dataset Arabic/English evaluation suite (`backend/src/commerce_ai/adapters/observability/`, `backend/tests/evals/`)
- [ ] **Feature 4.2**: Multi-stage Dockerfiles, `docker-compose.yml` (`PostgreSQL` + `Redis`), `GitHub Actions` CI workflow, and `AWS App Runner / ECS Fargate` deployment templates & handover runbook (`infra/`, `docker-compose.yml`, `.github/workflows/ci.yml`)

---

## Post-MVP Expansion Horizon (Uncommitted — Schedule via `sdd-replan`)
- **Enterprise B2B Catalog & ERP Adapter**: Connect client-owned product databases, Salla/Zid/Shopify APIs, or SAP/Odoo `OData` feeds as native `CatalogProvider` plugins with per-tenant scoring weights.
- **Embeddable B2B Storefront Widget**: Lightweight `<script>` web component for enterprise e-commerce sites.
- **Regional Messaging Channels**: WhatsApp Business Cloud API and Telegram bot adapters calling `/api/v1/chat`.
- **Semantic Caching & Price Alerts**: `pgvector` semantic query cache and opt-in price-drop notifications.
