# Backlog: Phase 2 Post-LLM Prose Validation & Distributed Rate Limiting

- **Date**: 2026-11-15
- **Raised during**: Phase 2 Deep Review (`phase/2-agent-and-api`)
- **Status**: Open
- **Type**: Tech debt / Risk

## Question / Idea
Should we defer two multi-instance production and post-generation hardening enhancements raised during the Phase 2 4-lens deep review to **Phase 4** (`Feature 4.1` / `Feature 4.2`), rather than expanding Phase 2's MVP scope? Specifically:
1. **Redis-backed distributed sliding-window rate limiter (`#56`, `#57`)**: Upgrade `SlidingWindowRateLimitMiddleware` (`backend/src/commerce_ai/api/middleware.py`) from process-local bounded `OrderedDict` buckets to a Redis-backed distributed sliding window when `REDIS_URL` is configured, so multi-container AWS App Runner / ECS Fargate deployments enforce a global per-client RPM ceiling instead of scaling `N * rate_limit_rpm` across workers.
2. **Post-LLM output prose validation on `ChatResponse.reply` / `clarification_question` (`#57`)**: Add lightweight deterministic output filtering in `ShoppingAssistantWorkflow._node_explain` (`backend/src/commerce_ai/agent/graph.py`) and `extract_turn_intent` `CLARIFY` (`backend/src/commerce_ai/agent/intent.py`) to catch unverified external URLs or accidental system-prompt leakage markers inside Call #1/#2 prose while keeping `top_offers` strictly verified (`INV-05`).

## Context
- **Relevant files & specs**:
  - `backend/src/commerce_ai/api/middleware.py` (`SlidingWindowRateLimiter`, `SlidingWindowRateLimitMiddleware`)
  - `backend/src/commerce_ai/adapters/cache/redis_store.py` (`RedisCacheStore`, `REDIS_URL`)
  - `backend/src/commerce_ai/agent/graph.py` (`ShoppingAssistantWorkflow._node_explain`)
  - `backend/src/commerce_ai/agent/intent.py` (`extract_turn_intent`, `CLARIFY`)
  - `spec/features/feature-203-fastapi-service-and-contracts/plan.md` (§8 `In-memory sliding-window rate limiter scope`)
  - `spec/roadmap.md` (`Phase 4` → `Feature 4.1` & `Feature 4.2`)
- **Constraints & Invariants (`spec/tech.md`)**:
  - `INV-01`: Zero leaked secrets or internal prompts.
  - `INV-04`: Bounded execution & cost ceiling (`rate_limit_rpm`, `<= 2` LLM calls/turn).
  - `INV-05`: Zero hallucinated offers (`top_offers` remains strictly unmodified from `rank_top_offers`, while prose validation would add defense-in-depth on `reply` / `clarification_question`).
  - `INV-08`: Graceful degradation (Redis rate-limiter fallback to in-memory limiter if Redis is unavailable).

## Findings
1. **Process-local rate limiter (`backend/src/commerce_ai/api/middleware.py:78-153`)**: Currently uses an in-memory `OrderedDict` per worker process (`Feature 2.3` MVP scope). In multi-container AWS deployments (`Feature 4.2`), each instance enforces `rate_limit_rpm` independently unless backed by Redis or an edge AWS WAF rate rule. Note: Phase 2 already hardens `X-Forwarded-For` handling via `AppSettings.trusted_proxy_cidrs` right-to-left untrusted hop extraction.
2. **Unfiltered LLM prose (`backend/src/commerce_ai/agent/graph.py:474-476`, `intent.py:771-784`)**: While `ChatResponse.top_offers` is strictly grounded and unmodified from `rank_top_offers` (`INV-05`), Call #2 `reply` prose and Call #1 `clarification_question` pass through `.strip()` without checking for unverified third-party URLs or prompt-leakage markers.

## Recommendations
| # | Recommendation | Human decision (accepted / changed / rejected) |
|:---|:---|:---|
| 1 | Implement an optional Redis-backed sliding-window rate limiter (Lua/sorted-set with graceful fallback to in-memory `SlidingWindowRateLimiter` per `INV-08`) alongside AWS WAF edge rate limiting in Phase 4 (`Feature 4.2`). | accepted (deferred to Phase 4 out-of-scope backlog during Phase 2 deep-review fixes) |
| 2 | Add lightweight post-LLM prose URL/prompt-leakage validation on `ChatResponse.reply` (falling back to `templates.py` on violation) and `clarification_question` alongside Phase 4 golden evaluations (`Feature 4.1`). | accepted (deferred to Phase 4 out-of-scope backlog during Phase 2 deep-review fixes) |

## Next Step
Schedule into **Phase 4** (`Feature 4.1` for post-LLM prose guardrails + eval coverage, `Feature 4.2` for Redis distributed rate limiting + WAF deployment templates) via `sdd-replan` Mode B when opening Phase 4.
