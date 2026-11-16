"""Versioned FastAPI REST routes for chat, zero-LLM search, markets, and health."""

import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request

from commerce_ai.agent.graph import ShoppingAssistantWorkflow
from commerce_ai.api.dependencies import (
    get_catalog_provider,
    get_request_id,
    get_settings,
    get_workflow,
)
from commerce_ai.api.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    MarketInfoSchema,
    MarketsResponse,
    MarketStoreSchema,
    SearchRequest,
    SearchResponse,
)
from commerce_ai.config.markets import MARKET_REGISTRY
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.models import CountryCode, SearchIntent, StoreId
from commerce_ai.domain.ports import CatalogProvider
from commerce_ai.domain.ranking import rank_top_offers

router = APIRouter()

_MARKET_DISPLAY_METADATA: dict[CountryCode, dict[str, str]] = {
    CountryCode.EG: {
        "name_en": "Egypt",
        "name_ar": "مصر",
        "currency_label_en": "EGP",
        "currency_label_ar": "جنيه مصري",
    },
    CountryCode.SA: {
        "name_en": "Saudi Arabia",
        "name_ar": "السعودية",
        "currency_label_en": "SAR",
        "currency_label_ar": "ريال سعودي",
    },
    CountryCode.AE: {
        "name_en": "United Arab Emirates",
        "name_ar": "الإمارات",
        "currency_label_en": "AED",
        "currency_label_ar": "درهم إماراتي",
    },
}

_CHAT_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "Invalid request structure"},
    429: {"model": ErrorResponse, "description": "Per-client rate limit exceeded"},
    500: {"model": ErrorResponse, "description": "Unexpected internal error"},
}

_SEARCH_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "Invalid search parameters"},
    429: {"model": ErrorResponse, "description": "Per-client rate limit exceeded"},
    503: {"model": ErrorResponse, "description": "Upstream catalog provider unavailable"},
    500: {"model": ErrorResponse, "description": "Unexpected internal error"},
}

_DEFAULT_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"model": ErrorResponse, "description": "Unexpected internal error"},
}


@router.post(
    "/api/v1/chat",
    response_model=ChatResponse,
    tags=["chat"],
    summary="Execute one bounded conversational shopping turn",
    responses=_CHAT_RESPONSES,
)
async def chat_turn(
    payload: ChatRequest,
    workflow: Annotated[ShoppingAssistantWorkflow, Depends(get_workflow)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ChatResponse:
    """Delegate conversational shopping turn to the bounded LangGraph workflow."""
    turn_result = await workflow.run_turn(
        message=payload.message,
        session_id=payload.session_id,
        default_country=payload.country,
        store_override=payload.store,
        max_budget_override=payload.max_budget,
        language_hint=payload.language,
    )
    return ChatResponse(
        session_id=turn_result.session_id,
        status=turn_result.status,
        reply=turn_result.reply,
        action=turn_result.action,
        active_intent=turn_result.active_intent,
        top_offers=turn_result.top_offers,
        ranking_result=turn_result.ranking_result,
        telemetry=turn_result.telemetry,
        request_id=request_id,
    )


@router.post(
    "/api/v1/search",
    response_model=SearchResponse,
    tags=["search"],
    summary="Execute direct zero-LLM deterministic Top-3 catalog search",
    responses=_SEARCH_RESPONSES,
)
async def direct_search(
    payload: SearchRequest,
    settings: Annotated[AppSettings, Depends(get_settings)],
    catalog_provider: Annotated[CatalogProvider, Depends(get_catalog_provider)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> SearchResponse:
    """Search regional Noon/Amazon offers and rank Top-3 deterministically with 0 LLM calls."""
    started = time.perf_counter()
    intent = SearchIntent(
        query=payload.query,
        country=payload.country,
        store=payload.store,
        max_budget=payload.max_budget,
        min_rating=payload.min_rating,
        include_accessories=payload.include_accessories,
        language=payload.language,
    )
    catalog_result = await catalog_provider.search_offers(intent)
    ranking_result = rank_top_offers(
        catalog_result.offers,
        intent,
        config=settings.scoring,
    )
    latency_ms = round(max(0.0, (time.perf_counter() - started) * 1000.0), 3)
    return SearchResponse(
        intent=intent,
        ranking_result=ranking_result,
        source_mode=catalog_result.source_mode,
        cache_hit=catalog_result.cache_hit,
        latency_ms=latency_ms,
        request_id=request_id,
    )


@router.get(
    "/api/v1/markets",
    response_model=MarketsResponse,
    tags=["markets"],
    summary="List supported regional markets, currencies, and stores",
    responses=_DEFAULT_RESPONSES,
)
async def list_markets(
    request_id: Annotated[str, Depends(get_request_id)],
) -> MarketsResponse:
    """Return bilingual market metadata dynamically populated from MARKET_REGISTRY."""
    markets: list[MarketInfoSchema] = []
    for country in CountryCode:
        config = MARKET_REGISTRY[country]
        labels = _MARKET_DISPLAY_METADATA[country]
        stores = [
            MarketStoreSchema(
                store_id=StoreId.NOON,
                label_en="Noon",
                label_ar="نون",
                primary_domain=config.noon_host,
            ),
            MarketStoreSchema(
                store_id=StoreId.AMAZON,
                label_en="Amazon",
                label_ar="أمازون",
                primary_domain=config.amazon_domains[0],
            ),
        ]
        markets.append(
            MarketInfoSchema(
                country=config.country,
                currency=config.currency,
                name_en=labels["name_en"],
                name_ar=labels["name_ar"],
                currency_label_en=labels["currency_label_en"],
                currency_label_ar=labels["currency_label_ar"],
                serper_gl=config.serper_gl,
                stores=stores,
            )
        )
    return MarketsResponse(markets=markets, request_id=request_id)


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Report non-sensitive service health and backend degradation status",
    responses=_DEFAULT_RESPONSES,
)
async def health_check(
    request: Request,
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> HealthResponse:
    """Expose secret-free operational modes and active cache/session backends."""
    cache_backend = str(getattr(request.app.state, "cache_backend", "custom"))
    cache_degraded = bool(getattr(request.app.state, "cache_degraded", False))

    repo = getattr(request.app.state, "session_repository", None)
    if repo is not None and hasattr(repo, "backend_name") and hasattr(repo, "is_degraded"):
        session_backend = str(repo.backend_name)
        session_degraded = bool(repo.is_degraded)
    else:
        session_backend = str(getattr(request.app.state, "session_backend", "custom"))
        session_degraded = bool(getattr(request.app.state, "session_degraded", False))

    status: Literal["ok", "degraded"] = "degraded" if (cache_degraded or session_degraded) else "ok"
    return HealthResponse(
        status=status,
        app_env=settings.app_env,
        catalog_mode=settings.catalog_mode,
        llm_mode=settings.llm_mode,
        cache_backend=cache_backend,
        session_backend=session_backend,
        version="0.1.0",
    )
