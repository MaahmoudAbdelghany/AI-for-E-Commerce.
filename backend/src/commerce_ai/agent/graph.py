"""Bounded LangGraph multi-turn shopping workflow orchestrating guardrails, memory, and ranking."""

import logging
import re
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from commerce_ai.agent.guardrails import check_input_guardrails
from commerce_ai.agent.intent import extract_turn_intent
from commerce_ai.agent.prompts import build_explanation_request
from commerce_ai.agent.templates import (
    render_clarification_message,
    render_comparison_summary,
    render_degraded_catalog_message,
    render_off_topic_message,
    render_offers_summary,
    render_refused_message,
)
from commerce_ai.config.scoring import ScoringConfig
from commerce_ai.config.settings import AppSettings, redact_url_password
from commerce_ai.domain.errors import CatalogProviderError, LLMProviderError, SessionStoreError
from commerce_ai.domain.models import (
    CatalogSearchResult,
    CatalogSourceMode,
    ChatTurnResult,
    CountryCode,
    ProductOffer,
    RankedOffer,
    RankingResult,
    SearchIntent,
    SessionState,
    SessionTurn,
    StoreFilter,
    TurnAction,
    TurnStatus,
    TurnTelemetry,
)
from commerce_ai.domain.ports import CatalogProvider, LLMClient, SessionRepository
from commerce_ai.domain.ranking import rank_top_offers

logger = logging.getLogger(__name__)

_URL_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"'<>]+")
_KV_SECRET_RE = re.compile(
    r"\b(password|passwd|pwd|secret|token|api[_-]?key)\b(\s*[:=]\s*)([^\s,;]+)",
    re.IGNORECASE,
)


def _scrub_log_text(text: str) -> str:
    """Mask connection-string passwords and secret key-value tokens before logging."""

    def _replace_url(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        return redact_url_password(raw_url) or "***"

    masked_urls = _URL_TOKEN_RE.sub(_replace_url, text)
    return _KV_SECRET_RE.sub(r"\1\2***", masked_urls)


def _append_reason(reasons: list[str], reason: str | None) -> list[str]:
    if reason and reason not in reasons:
        reasons.append(reason)
    return reasons


class _WorkflowState(TypedDict, total=False):
    raw_message: str
    session_id: str
    default_country: CountryCode
    store_override: StoreFilter | None
    max_budget_override: Decimal | None
    language_hint: Literal["ar", "en"] | None

    guard_allowed: bool
    guard_reason_code: str | None
    sanitized_message: str
    language: Literal["ar", "en"]

    loaded_session: SessionState | None

    action: TurnAction
    active_intent: SearchIntent | None
    clarification_question: str | None
    used_rule_intent_fallback: bool
    llm_calls: int
    degraded_reasons: list[str]

    missing_saved_offers_for_compare: bool
    route_target: Literal["respond_guard_or_clarify", "fetch_catalog", "compare_saved"]

    catalog_called: bool
    catalog_cache_hit: bool
    catalog_source_mode: CatalogSourceMode | None
    catalog_offers: tuple[ProductOffer, ...]
    catalog_degraded: bool

    ranking_result: RankingResult | None
    top_offers: list[RankedOffer]
    degraded_fewer_than_k: bool

    status: TurnStatus
    reply: str
    used_template_summary: bool


class ShoppingAssistantWorkflow:
    """Bounded LangGraph agent executing guard -> session -> parse -> route -> respond/explain."""

    def __init__(
        self,
        settings: AppSettings,
        catalog_provider: CatalogProvider,
        session_repository: SessionRepository,
        llm_client: LLMClient | None = None,
        scoring_config: ScoringConfig | None = None,
    ) -> None:
        self._settings = settings
        self._catalog_provider = catalog_provider
        self._session_repository = session_repository
        self._llm_client = llm_client
        self._scoring_config = scoring_config or settings.scoring
        self._compiled_graph = self._build_graph()

    @property
    def compiled_graph(self) -> Any:
        """Expose compiled LangGraph graph for inspection and diagnostics."""
        return self._compiled_graph

    def _build_graph(self) -> Any:
        graph = StateGraph(_WorkflowState)
        graph.add_node("guard", self._node_guard)
        graph.add_node("load_session", self._node_load_session)
        graph.add_node("parse", self._node_parse)
        graph.add_node("route", self._node_route)
        graph.add_node("respond_guard_or_clarify", self._node_respond_guard_or_clarify)
        graph.add_node("fetch_catalog", self._node_fetch_catalog)
        graph.add_node("rank_offers", self._node_rank_offers)
        graph.add_node("compare_saved", self._node_compare_saved)
        graph.add_node("explain", self._node_explain)
        graph.add_node("save_session", self._node_save_session)

        graph.add_edge(START, "guard")
        graph.add_conditional_edges(
            "guard",
            self._edge_after_guard,
            {
                "respond_guard_or_clarify": "respond_guard_or_clarify",
                "load_session": "load_session",
            },
        )
        graph.add_edge("load_session", "parse")
        graph.add_edge("parse", "route")
        graph.add_conditional_edges(
            "route",
            self._edge_after_route,
            {
                "respond_guard_or_clarify": "respond_guard_or_clarify",
                "fetch_catalog": "fetch_catalog",
                "compare_saved": "compare_saved",
            },
        )
        graph.add_conditional_edges(
            "respond_guard_or_clarify",
            self._edge_after_respond_guard_or_clarify,
            {
                "end": END,
                "save_session": "save_session",
            },
        )
        graph.add_conditional_edges(
            "fetch_catalog",
            self._edge_after_fetch_catalog,
            {
                "save_session": "save_session",
                "rank_offers": "rank_offers",
            },
        )
        graph.add_edge("rank_offers", "explain")
        graph.add_edge("compare_saved", "explain")
        graph.add_edge("explain", "save_session")
        graph.add_edge("save_session", END)

        return graph.compile()

    async def _node_guard(self, state: _WorkflowState) -> dict[str, Any]:
        guard_res = check_input_guardrails(
            state["raw_message"],
            max_chars=self._settings.guardrail_max_chars,
        )
        hint = state.get("language_hint")
        language: Literal["ar", "en"] = hint if hint is not None else guard_res.language
        if not guard_res.allowed:
            return {
                "guard_allowed": False,
                "guard_reason_code": guard_res.reason_code,
                "sanitized_message": "",
                "language": language,
                "action": TurnAction.REFUSE,
                "status": TurnStatus.REFUSED,
            }
        return {
            "guard_allowed": True,
            "guard_reason_code": None,
            "sanitized_message": guard_res.sanitized_message,
            "language": language,
        }

    def _edge_after_guard(self, state: _WorkflowState) -> str:
        if state.get("guard_allowed", False):
            return "load_session"
        return "respond_guard_or_clarify"

    async def _node_load_session(self, state: _WorkflowState) -> dict[str, Any]:
        session_id = state["session_id"]
        reasons = list(state.get("degraded_reasons", []))
        loaded: SessionState | None = None
        try:
            loaded = await self._session_repository.get_session(session_id)
        except SessionStoreError as exc:
            logger.warning("Session load failed cleanly: %s", _scrub_log_text(str(exc)))
            _append_reason(reasons, "session_load_error")

        if loaded is None:
            loaded = SessionState(session_id=session_id, market=state["default_country"])
        return {
            "loaded_session": loaded,
            "degraded_reasons": reasons,
        }

    async def _node_parse(self, state: _WorkflowState) -> dict[str, Any]:
        loaded = state.get("loaded_session") or SessionState(
            session_id=state["session_id"],
            market=state["default_country"],
        )
        recent_turns = list(loaded.turns[-6:])
        has_saved_offers = len(loaded.last_ranked_offers) > 0

        intent_res = await extract_turn_intent(
            state["sanitized_message"],
            default_country=state["default_country"],
            store_override=state.get("store_override"),
            max_budget_override=state.get("max_budget_override"),
            language_hint=state.get("language_hint"),
            prior_intent=loaded.last_intent,
            recent_turns=recent_turns,
            has_saved_offers=has_saved_offers,
            llm_client=self._llm_client,
        )

        reasons = _append_reason(
            list(state.get("degraded_reasons", [])),
            intent_res.degraded_reason,
        )
        llm_calls = min(2, state.get("llm_calls", 0) + intent_res.llm_calls_used)
        return {
            "action": intent_res.action,
            "active_intent": intent_res.intent,
            "language": intent_res.language,
            "clarification_question": intent_res.clarification_question,
            "used_rule_intent_fallback": intent_res.used_rule_fallback,
            "llm_calls": llm_calls,
            "degraded_reasons": reasons,
        }

    async def _node_route(self, state: _WorkflowState) -> dict[str, Any]:
        action = state["action"]
        active_intent = state.get("active_intent")
        loaded = state.get("loaded_session")

        if action in {TurnAction.CLARIFY, TurnAction.OFF_TOPIC, TurnAction.REFUSE}:
            return {
                "route_target": "respond_guard_or_clarify",
                "missing_saved_offers_for_compare": False,
            }

        if action == TurnAction.COMPARE:
            if loaded is not None and len(loaded.last_ranked_offers) > 0:
                return {
                    "route_target": "compare_saved",
                    "missing_saved_offers_for_compare": False,
                }
            # Transition COMPARE with no saved offers cleanly to CLARIFY with 0 catalog calls.
            return {
                "action": TurnAction.CLARIFY,
                "route_target": "respond_guard_or_clarify",
                "missing_saved_offers_for_compare": True,
            }

        if active_intent is None:
            return {
                "action": TurnAction.CLARIFY,
                "route_target": "respond_guard_or_clarify",
                "missing_saved_offers_for_compare": False,
            }

        return {
            "route_target": "fetch_catalog",
            "missing_saved_offers_for_compare": False,
        }

    def _edge_after_route(self, state: _WorkflowState) -> str:
        return state["route_target"]

    async def _node_respond_guard_or_clarify(self, state: _WorkflowState) -> dict[str, Any]:
        action = state["action"]
        language = state["language"]

        if action == TurnAction.REFUSE:
            reply = render_refused_message(
                language=language,
                reason_code=state.get("guard_reason_code"),
            )
            status = TurnStatus.REFUSED
        elif action == TurnAction.OFF_TOPIC:
            reply = render_off_topic_message(language=language)
            status = TurnStatus.OFF_TOPIC
        else:
            reply = render_clarification_message(
                language=language,
                question=state.get("clarification_question"),
                missing_saved_offers_for_compare=bool(
                    state.get("missing_saved_offers_for_compare", False)
                ),
            )
            status = TurnStatus.CLARIFY

        return {
            "status": status,
            "reply": reply,
            "top_offers": [],
            "ranking_result": None,
            "used_template_summary": True,
        }

    def _edge_after_respond_guard_or_clarify(self, state: _WorkflowState) -> str:
        if state.get("status") == TurnStatus.REFUSED:
            return "end"
        return "save_session"

    async def _node_fetch_catalog(self, state: _WorkflowState) -> dict[str, Any]:
        intent = state.get("active_intent")
        language = state["language"]
        if intent is None:
            return {
                "catalog_called": False,
                "catalog_cache_hit": False,
                "catalog_source_mode": None,
                "catalog_offers": (),
                "catalog_degraded": True,
                "status": TurnStatus.CLARIFY,
                "top_offers": [],
                "ranking_result": None,
                "reply": render_clarification_message(language=language),
                "used_template_summary": True,
            }

        try:
            catalog_result: CatalogSearchResult = await self._catalog_provider.search_offers(intent)
        except CatalogProviderError as exc:
            logger.warning(
                "Catalog provider failed (%s, retriable=%s): %s",
                exc.provider,
                exc.retriable,
                _scrub_log_text(exc.reason or str(exc)),
            )
            reasons = _append_reason(
                list(state.get("degraded_reasons", [])),
                f"catalog_provider_error:{exc.provider}",
            )
            return {
                "catalog_called": True,
                "catalog_cache_hit": False,
                "catalog_source_mode": None,
                "catalog_offers": (),
                "catalog_degraded": True,
                "status": TurnStatus.DEGRADED,
                "top_offers": [],
                "ranking_result": None,
                "reply": render_degraded_catalog_message(
                    language=language,
                    retriable=exc.retriable,
                ),
                "used_template_summary": True,
                "degraded_reasons": reasons,
            }

        return {
            "catalog_called": True,
            "catalog_cache_hit": catalog_result.cache_hit,
            "catalog_source_mode": catalog_result.source_mode,
            "catalog_offers": catalog_result.offers,
            "catalog_degraded": False,
        }

    def _edge_after_fetch_catalog(self, state: _WorkflowState) -> str:
        if state.get("catalog_degraded", False):
            return "save_session"
        return "rank_offers"

    async def _node_rank_offers(self, state: _WorkflowState) -> dict[str, Any]:
        intent = state["active_intent"]
        assert intent is not None
        offers = state.get("catalog_offers", ())
        ranking_result = rank_top_offers(offers, intent, config=self._scoring_config)
        return {
            "ranking_result": ranking_result,
            "top_offers": list(ranking_result.ranked_offers),
            "degraded_fewer_than_k": ranking_result.degraded_fewer_than_k,
        }

    async def _node_compare_saved(self, state: _WorkflowState) -> dict[str, Any]:
        loaded = state.get("loaded_session")
        saved_offers = list(loaded.last_ranked_offers) if loaded is not None else []
        return {
            "catalog_called": False,
            "catalog_cache_hit": False,
            "catalog_source_mode": None,
            "ranking_result": None,
            "top_offers": saved_offers,
            "degraded_fewer_than_k": False,
        }

    def _should_call_explain_llm(self, state: _WorkflowState) -> bool:
        if self._llm_client is None:
            return False
        if len(state.get("top_offers", [])) == 0:
            return False
        if state.get("llm_calls", 0) >= 2:
            return False
        explain_mode = self._settings.explain_mode
        if explain_mode == "template":
            return False
        if explain_mode == "llm":
            return True
        if any(
            reason.startswith("llm_provider_error:") for reason in state.get("degraded_reasons", [])
        ):
            return False
        # "auto": Call #2 only on uncached searches or saved-offer comparisons.
        return state["action"] == TurnAction.COMPARE or not state.get("catalog_cache_hit", False)

    def _render_deterministic_summary(self, state: _WorkflowState) -> str:
        top_offers = state.get("top_offers", [])
        language = state["language"]
        if state["action"] == TurnAction.COMPARE:
            return render_comparison_summary(top_offers, language=language)
        return render_offers_summary(
            top_offers,
            language=language,
            degraded_fewer_than_k=bool(state.get("degraded_fewer_than_k", False)),
            intent=state.get("active_intent"),
        )

    async def _node_explain(self, state: _WorkflowState) -> dict[str, Any]:
        top_offers = state.get("top_offers", [])
        language = state["language"]
        action = state["action"]
        reasons = list(state.get("degraded_reasons", []))
        llm_calls = state.get("llm_calls", 0)

        if self._should_call_explain_llm(state) and self._llm_client is not None:
            request = build_explanation_request(
                top_offers,
                intent=state.get("active_intent"),
                action=action,
                language=language,
                degraded_fewer_than_k=bool(state.get("degraded_fewer_than_k", False)),
                max_tokens=300,
            )
            llm_calls = min(2, llm_calls + 1)
            try:
                response = await self._llm_client.complete(request)
                cleaned_reply = response.content.strip()
                if cleaned_reply:
                    return {
                        "status": TurnStatus.OK,
                        "reply": cleaned_reply,
                        "used_template_summary": False,
                        "llm_calls": llm_calls,
                        "degraded_reasons": reasons,
                    }
                _append_reason(reasons, "llm_explain_empty")
            except LLMProviderError as exc:
                logger.warning(
                    "Explain LLM call failed (%s, retriable=%s): %s",
                    exc.provider,
                    exc.retriable,
                    _scrub_log_text(exc.reason or str(exc)),
                )
                _append_reason(reasons, f"llm_explain_error:{exc.provider}")

        return {
            "status": TurnStatus.OK,
            "reply": self._render_deterministic_summary(state),
            "used_template_summary": True,
            "llm_calls": llm_calls,
            "degraded_reasons": reasons,
        }

    async def _node_save_session(self, state: _WorkflowState) -> dict[str, Any]:
        loaded = state.get("loaded_session") or SessionState(
            session_id=state["session_id"],
            market=state["default_country"],
        )
        action = state["action"]
        status = state["status"]
        active_intent = state.get("active_intent")
        is_successful_search = (
            action == TurnAction.SEARCH and status == TurnStatus.OK and active_intent is not None
        )

        next_market = (
            active_intent.country if is_successful_search and active_intent else loaded.market
        )
        next_intent = active_intent if is_successful_search else loaded.last_intent
        next_offers = (
            list(state.get("top_offers", []))
            if is_successful_search
            else list(loaded.last_ranked_offers)
        )

        now_iso = datetime.now(UTC).isoformat()
        updated_turns = [
            *loaded.turns,
            SessionTurn(
                role="user",
                content=state["sanitized_message"],
                action=action,
                created_at_iso=now_iso,
            ),
            SessionTurn(
                role="assistant",
                content=state["reply"],
                action=action,
                created_at_iso=now_iso,
            ),
        ]
        max_turns = max(2, self._settings.session_max_turns)
        trimmed_turns = updated_turns[-max_turns:]

        next_state = SessionState(
            session_id=loaded.session_id,
            market=next_market,
            last_intent=next_intent,
            last_ranked_offers=next_offers,
            turns=trimmed_turns,
            updated_at_epoch=time.time(),
        )

        reasons = list(state.get("degraded_reasons", []))
        try:
            await self._session_repository.save_session(
                next_state,
                ttl_seconds=self._settings.session_ttl_seconds,
            )
        except SessionStoreError as exc:
            logger.warning("Session save failed cleanly: %s", _scrub_log_text(str(exc)))
            _append_reason(reasons, "session_save_error")

        return {"degraded_reasons": reasons}

    async def run_turn(
        self,
        *,
        message: str,
        session_id: str | None = None,
        default_country: CountryCode = CountryCode.EG,
        store_override: StoreFilter | None = None,
        max_budget_override: Decimal | None = None,
        language_hint: Literal["ar", "en"] | None = None,
    ) -> ChatTurnResult:
        """Run one bounded conversational shopping turn and return verified ChatTurnResult."""
        started = time.perf_counter()
        effective_session_id = (
            session_id.strip()
            if session_id is not None and session_id.strip()
            else str(uuid.uuid4())
        )
        initial_state: _WorkflowState = {
            "raw_message": message,
            "session_id": effective_session_id,
            "default_country": default_country,
            "store_override": store_override,
            "max_budget_override": max_budget_override,
            "language_hint": language_hint,
            "llm_calls": 0,
            "degraded_reasons": [],
            "catalog_called": False,
            "catalog_cache_hit": False,
            "catalog_source_mode": None,
            "used_rule_intent_fallback": False,
            "used_template_summary": False,
            "top_offers": [],
            "ranking_result": None,
        }

        final_state = cast(_WorkflowState, await self._compiled_graph.ainvoke(initial_state))
        latency_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        reasons = final_state.get("degraded_reasons", [])

        telemetry = TurnTelemetry(
            llm_calls=min(2, max(0, int(final_state.get("llm_calls", 0)))),
            catalog_called=bool(final_state.get("catalog_called", False)),
            catalog_cache_hit=bool(final_state.get("catalog_cache_hit", False)),
            catalog_source_mode=final_state.get("catalog_source_mode"),
            used_rule_intent_fallback=bool(final_state.get("used_rule_intent_fallback", False)),
            used_template_summary=bool(final_state.get("used_template_summary", False)),
            degraded_reason="; ".join(reasons) if reasons else None,
            latency_ms=round(latency_ms, 3),
        )

        return ChatTurnResult(
            session_id=effective_session_id,
            status=final_state["status"],
            reply=final_state["reply"],
            action=final_state["action"],
            active_intent=final_state.get("active_intent"),
            top_offers=list(final_state.get("top_offers", [])),
            ranking_result=final_state.get("ranking_result"),
            telemetry=telemetry,
        )
