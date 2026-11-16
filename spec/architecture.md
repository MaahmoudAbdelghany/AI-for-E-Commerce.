# System Architecture (HLD) — AI for E-Commerce

> Complements `spec/mission.md` and `spec/tech.md`. Designed for **minimum cost**, **low latency**, and **clean B2C-to-B2B extensibility**.

---

## 1. High-Level Component Diagram

```mermaid
flowchart TD
    User["Shopper / Enterprise Buyer (EG, SA, AE)"] -->|"Arabic RTL / English"| WebUI["Next.js 15 RTL Web App (Chat + Top-3 Cards)"]
    B2BFuture["Future Channels (B2B Widget / WhatsApp)"] -.->|"REST / SSE"| API

    WebUI -->|"POST /api/v1/chat"| API["FastAPI Gateway & Pydantic v2 Contracts"]

    subgraph CoreEngine["AI for E-Commerce Core (Hexagonal Python Backend)"]
        API --> Guard["Input Guardrails & Sanitizer"]
        Guard --> Graph["Bounded LangGraph Workflow"]
        Graph --> SessionPort["SessionRepository Port"]
        Graph --> Router["Model Router (LLMClient Port)"]
        Graph --> CatalogPort["CatalogProvider Port"]
        Graph --> Ranker["Deterministic Value Scorer & Anti-Accessory Filter"]
    end

    subgraph Adapters["Pluggable Infrastructure Adapters"]
        SessionPort --> DB["PostgreSQL 16 (Prod) / SQLite (Dev & CI)"]
        CatalogPort --> Cache["Redis 7 TTL Cache / In-Memory Cache"]
        Cache -->|"Cache Miss"| Serper["Serper Shopping API (Noon & Amazon EG/SA/AE)"]
        Cache -->|"Offline / Demo Mode"| Seed["SeedCatalogProvider (Curated MENA Fixtures)"]
        CatalogPort -.->|"Post-MVP Plugin"| ERP["Merchant DB / ERP / Salla / SAP OData"]
        Router --> FastLLM["Tier-1 Fast LLM (Gemini 2.5 Flash / Groq / Bedrock Haiku)"]
        CoreEngine --> Obs["Langfuse Tracing & Cost Telemetry"]
    end
```

---

## 2. End-to-End Request & Degradation Sequence

```mermaid
sequenceDiagram
    actor U as User (Arabic/English)
    participant UI as Next.js RTL UI
    participant API as FastAPI (/api/v1/chat)
    participant LG as LangGraph Workflow
    participant LLM as Fast LLM (Tier-1)
    participant CACHE as Redis / TTL Cache
    participant CAT as CatalogProvider (Serper / Seed)
    participant RANK as Deterministic Scorer

    U->>UI: "عايز سماعة بلوتوث أنكر من نون مصر بأرخص سعر وأعلى تقييم"
    UI->>API: POST /api/v1/chat (message, session_id, market="EG")
    API->>LG: Invoke bounded state graph
    LG->>LLM: Call #1 — Extract structured SearchIntent (JSON schema)
    LLM-->>LG: {query: "Anker Bluetooth Earbuds", store: "noon", country: "EG", exclude: ["case","cover","جراب"]}

    alt Intent is critically ambiguous (e.g., no product category at all)
        LG-->>API: Clarification prompt (1 short Arabic question)
        API-->>UI: Ask user to clarify product
    else Intent is actionable
        LG->>CACHE: Lookup catalog_cache_key() (eg:noon:en:anker-bluetooth-earbuds)
        alt Cache Hit (< 50 ms)
            CACHE-->>LG: Cached list[ProductOffer]
        else Cache Miss
            LG->>CAT: search_offers(intent) with 2.0s timeout
            alt External API Healthy
                CAT-->>LG: Raw marketplace offers (Noon EG / Amazon EG)
                LG->>CACHE: Store offers with TTL (e.g., 15–60 min)
            else External API Timeout / Error (Graceful Degradation)
                CAT-->>LG: ProviderError
                LG-->>API: Degraded status + transparent retry/fallback message (zero hallucinated offers)
            end
        end

        LG->>RANK: rank_top_offers(offers, intent, config) (top_k = 3)
        RANK-->>LG: Top-3 RankedOffer (value_score, bayesian_rating, price_norm, match_reasons)
        LG->>LLM: Call #2 (Optional/Lightweight) — Concise Arabic recommendation summary
        LLM-->>LG: Grounded summary referencing only the 3 verified offers
        LG-->>API: ChatResponse (reply, top_offers, telemetry)
        API-->>UI: Render RTL message + 3 Comparison Cards + Outbound Store Links
    end
```

---

## 3. Deterministic Value Scoring Formula (`INV-03`)

To avoid both the **"Cheap Accessory Trap"** and the **"1-Review 5-Star Trap"** without spending LLM tokens on math:

1. **Hard Filtering Stage**:
   - Reject offers lacking a valid positive price or verified product URL.
   - Reject accessories when the user searched for a primary product (negative keyword list + configurable median-price floor, e.g., rejecting items priced `< 15%` of the candidate set's median price unless explicitly requested).
   - Apply user-stated `max_budget`, `min_rating`, and `store` (`noon` / `amazon`) filters.

2. **Bayesian Confidence-Adjusted Rating ($R_{\text{adj}}$)**:
   $$R_{\text{adj}} = \frac{v}{v + m} \cdot R + \frac{m}{v + m} \cdot C$$
   Where $R$ is the item's star rating ($0\text{–}5$), $v$ is its review count, $m$ is the configurable prior review threshold (default `m = 25`), and $C$ is the prior mean rating across candidates (default `C = 4.0`). A product with `4.8` stars across `600` reviews reliably outranks a `5.0` star listing with `1` review.

3. **Composite Value Score ($S_{\text{value}} \in [0, 100]$)**:
   $$P_{\text{norm}} = \frac{P_{\max} - P}{P_{\max} - P_{\min} + \epsilon}, \qquad R_{\text{norm}} = \frac{R_{\text{adj}}}{5.0}$$
   $$S_{\text{value}} = 100 \times \left( w_{\text{price}} \cdot P_{\text{norm}} + w_{\text{rating}} \cdot R_{\text{norm}} \right)$$
   Default balanced MVP weights: `w_price = 0.55`, `w_rating = 0.45` (configurable per request mode or B2B tenant profile). Ties break by higher review count $v$, then lower price $P$.

---

## 4. Model Routing & Cost Control Policy (`INV-04`)

| Task | Model Tier | Default Candidates | Token Budget | Fallback |
|:---|:---|:---|:---|:---|
| Structured Intent & Filter Extraction | **Tier-1 Ultra-Fast / Low-Cost** | `gemini-2.5-flash` / `llama-3.3-70b` (Groq) / `claude-3-5-haiku` (AWS Bedrock) | `<= 350` output tokens (strict JSON schema) | Rule-based keyword + regex parser |
| Top-3 Comparison Summary (Arabic/English) | **Tier-1 Ultra-Fast / Low-Cost** | Same Tier-1 model | `<= 300` output tokens | Deterministic Arabic/English template builder (0 tokens!) |
| Ranking, Price Math & Outlier Filtering | **Tier-0 Deterministic Python** | Pure Python (`domain/ranking.py`) | `0` tokens | N/A (in-process, `< 2 ms`) |

---

## 5. Architecture Decision Summary (ADRs)

- **ADR-01 (API-First Hexagonal Core)**: Decouples domain/agent logic from Next.js and Noon/Amazon adapters so the MVP serves B2C users immediately while remaining drop-in ready for B2B enterprise catalogs and WhatsApp/widget channels.
- **ADR-02 (Search/Shopping SERP API + TTL Cache over Direct Scraping)**: Eliminates anti-bot blocks, proxy expenses, legal/ToS friction, and `10s+` browser latency, cutting repeat search latency below `50 ms` via Redis caching.
- **ADR-03 (Deterministic Bayesian Value Score over LLM Ranking)**: Guarantees reproducible math, prevents 1-review gaming, saves ~80% of prompt tokens, and allows non-developer weight tuning.
- **ADR-04 (Bounded `LangGraph` over Open `ReAct` Agent)**: Caps latency and cost at `<= 2` fast LLM calls per turn while preserving conversational session state.
- **ADR-05 (Docker on AWS App Runner / ECS Fargate)**: Achieves serverless container economics on AWS (no idle `$73+/mo` EKS cluster fee, no Lambda streaming cold starts) while keeping 100% Docker portability for on-premise Gulf/Egyptian enterprise deployments.
