# Project Mission — AI for E-Commerce

> Status: Draft (Pending Human Constitution Approval)
> Markets: Egypt (`EG`), Saudi Arabia (`SA`), United Arab Emirates (`AE`)

## 1. Product (What)
**AI for E-Commerce** is an **API-First AI Shopping Advisor & Value-Comparison Engine** paired with a fast, Arabic-first (`RTL`) web interface.

Instead of manually browsing multiple marketplaces, filtering out irrelevant accessories, and cross-checking reviews, a shopper states what they want in natural Arabic (Egyptian, Gulf, or Modern Standard Arabic) or English—for example: *"عايز اشتري سماعة بلوتوث أنكر من نون بأرخص سعر وأعلى تقييم"*. The engine extracts structured shopping intent, queries supported marketplace catalogs (starting with **Noon** and **Amazon** across Egypt, Saudi Arabia, and the UAE), filters out accessories and rating traps, and returns the **Top 3 best-value products** combining the **lowest price** and **highest confidence-weighted rating**, complete with clear explanations and direct verified purchase links.

Because the core engine is strictly **API-First** and built around pluggable catalog, LLM, and storage interfaces, the exact same backend powers:
1. **B2C Multi-Store Deal Discovery** across Noon and Amazon today.
2. **B2B Enterprise Integration** tomorrow—plugging directly into a retailer's internal catalog, e-commerce platform, or ERP system to improve product discovery, customer service, and conversion.

## 2. Problem (Why)
1. **Manual Search Fatigue & Noise**: Shoppers on Noon and Amazon must manually sift through dozens of sponsored listings, duplicate sellers, and accessory clutter (e.g., searching for a smartphone sorted by lowest price surfaces phone cases and cables).
2. **Misleading Ratings vs. Price Trade-offs**: Sorting by "Price: Low to High" surfaces low-quality items, while sorting by "Avg. Customer Review" often surfaces overpriced items or products with a 5.0 rating from a single unverified review.
3. **High-Cost, Fragile Enterprise AI Prototypes**: Regional e-commerce companies in MENA want conversational AI shopping assistants, but naive open-ended LLM agents are too slow, hallucinate prices, and burn excessive token budgets.

## 3. Target Users (Who)
- **Primary MVP Users (B2C Shoppers)**: Price- and quality-conscious consumers in **Egypt (`EGP`)**, **Saudi Arabia (`SAR`)**, and **the UAE (`AED`)** shopping on Noon (`noon.com`) and Amazon (`amazon.eg`, `amazon.sa`, `amazon.ae`).
- **Strategic Enterprise Buyers (B2B / FDE Clients)**: E-commerce directors, marketplace operators, and customer-experience leaders in MENA enterprises seeking a scalable, low-cost, embeddable AI shopping and catalog-triage assistant.

## 4. Core Goal
Deliver an **MVP** that resolves a natural-language product request into **3 verified, high-rating, low-price product recommendations** with:
- **Minimum operating cost** (`<= $0.002` average LLM + search cost per uncached query; near-zero on cached queries).
- **High performance** (`<= 3.0 s` P95 latency on cache miss; `<= 300 ms` P95 on cache hit).
- **Clean, scalable, maintainable architecture** ready for AWS container production and future enterprise catalog/ERP onboarding without core rewrites.

## 5. Scope

### In Scope (MVP)
- **Natural-Language Intent & Conversational Refinement**: Understand product queries, brand/model constraints, budget caps, target store (`Noon`, `Amazon`, or `Both`), and country (`EG`, `SA`, `AE`) in Arabic dialects and English, with session memory for follow-ups (e.g., *"هات حاجة أرخص شوية"*, *"بدّل للسعودية"*, *"قارن بين الأول والثاني"*).
- **Pluggable Catalog Layer**: Abstract `CatalogProvider` supporting:
  - Live marketplace search via Search/Shopping SERP API targeting regional Noon and Amazon domains.
  - Redis / TTL caching to eliminate redundant external calls.
  - Deterministic Local Seed Catalog (`EG`/`SA`/`AE`) for offline testing, CI evaluations, and reliable B2B client demos.
- **Deterministic Top-3 Value Scoring Engine**: Configurable mathematical scoring combining normalized price and Bayesian-weighted rating (accounting for review volume), plus accessory and price-outlier filtering.
- **Bounded Agent Workflow & Model Routing**: Controlled `LangGraph` state machine routing extraction and concise explanation tasks to fast, low-cost LLMs (`Gemini Flash`, `Groq`, `OpenAI mini`, or `AWS Bedrock Haiku/Nova`).
- **Arabic-First (`RTL`) Web UI**: Lightweight `Next.js` interface featuring conversational chat, country/store selectors, side-by-side Top-3 comparison cards, value-score transparency, and outbound store links.
- **Production Readiness**: `Langfuse` tracing, automated evaluation dataset, multi-stage Dockerization, CI pipeline, and `AWS App Runner / ECS Fargate` deployment configuration.

### Out of Scope (MVP Exclusions)
- **In-App Checkout or Payment Processing**: The system never processes payments, carts, or credit cards; users complete purchases directly on Noon or Amazon via outbound links (zero PCI-DSS liability).
- **Direct HTML Scraping / Anti-Bot Bypassing**: No Playwright/Selenium scraping or CAPTCHA circumvention against Noon or Amazon storefronts.
- **End-User Accounts & Password Auth**: MVP uses lightweight session identifiers rather than mandatory user sign-up walls.
- **Messaging Bots & Live ERP Connectors in MVP**: WhatsApp/Telegram bots and direct SAP/Odoo/Salla connectors are deferred to post-MVP phases (enabled later as plug-in adapters).

## 6. Success Metrics
| Metric | MVP Target | How Measured |
|:---|:---|:---|
| End-to-end latency (cache miss) | `<= 3.0 s` at P95 | FastAPI request metrics & `Langfuse` traces |
| End-to-end latency (cache hit) | `<= 300 ms` at P95 | FastAPI integration benchmark |
| LLM + Search unit cost | `<= $0.002` per uncached query | `Langfuse` token cost tracking + cache hit ratio |
| Top-3 relevance & anti-accessory precision | `>= 90%` pass rate | Automated golden evaluation dataset (`backend/tests/evals/`) |
| Hallucinated prices / links | `0%` (strict zero tolerance) | Deterministic provenance check against `CatalogProvider` output |
| Offline test suite reliability | `100%` pass without network | `uv run pytest` in GitHub Actions CI |

## 7. Product Tone & UX Principles
- **Trusted Advisor, Not Hype**: Concise, objective, and transparent—clearly stating *why* each of the 3 products won (e.g., *"أرخص سعر مع ١٢٠٠ تقييم إيجابي"* vs. *"أعلى تقييم ٤.٨ بفارق سعري بسيط"*).
- **Native Arabic (`RTL`) First**: Natural, clear Arabic suitable for Egyptian and Gulf users, with seamless handling of English brand/model names (`iPhone 15`, `Anker`, `Samsung`) and effortless switching to English UI if desired.
- **Honest Degradation**: If a store has fewer than 3 matching products or live search is unavailable, explicitly inform the user rather than padding results with irrelevant items or invented data.
