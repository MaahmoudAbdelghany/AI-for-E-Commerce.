"""Strict Pydantic v2 REST request, response, and error contracts."""

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from commerce_ai.domain.models import (
    MAX_BUDGET_DECIMAL,
    CatalogSourceMode,
    CountryCode,
    CurrencyCode,
    RankedOffer,
    RankingResult,
    SearchIntent,
    StoreFilter,
    StoreId,
    TurnAction,
    TurnStatus,
    TurnTelemetry,
)


def _has_control_or_bidi_chars(value: str) -> bool:
    """Return True if value contains ASCII/C1 control, bidi-override/isolate, or Tag chars."""
    for ch in value:
        code = ord(ch)
        if code < 0x20 or 0x7F <= code <= 0x9F:
            return True
        if 0x202A <= code <= 0x202E or 0x2066 <= code <= 0x2069 or 0xE0000 <= code <= 0xE007F:
            return True
    return False


class ChatRequest(BaseModel):
    """Versioned chat turn payload delegating raw message checks to agent guardrails."""

    model_config = ConfigDict(extra="forbid")

    # Raw str lets empty, oversized, injection, and PII inputs reach workflow guardrails -> refused.
    message: str
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    country: CountryCode = CountryCode.EG
    store: StoreFilter | None = None
    max_budget: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        le=MAX_BUDGET_DECIMAL,
        allow_inf_nan=False,
    )
    language: Literal["ar", "en"] | None = None

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if _has_control_or_bidi_chars(value):
            raise ValueError("session_id must not contain control or bidi characters")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("session_id must not be blank")
        return cleaned


class ChatResponse(BaseModel):
    """Structured conversational response wrapping bounded workflow output."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: TurnStatus
    reply: str
    action: TurnAction
    active_intent: SearchIntent | None = None
    top_offers: list[RankedOffer] = Field(default_factory=list)
    ranking_result: RankingResult | None = None
    telemetry: TurnTelemetry
    request_id: str


class SearchRequest(BaseModel):
    """Structured direct search payload bypassing LLM extraction (0 LLM calls)."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    country: CountryCode = CountryCode.EG
    store: StoreFilter = StoreFilter.BOTH
    max_budget: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        le=MAX_BUDGET_DECIMAL,
        allow_inf_nan=False,
    )
    min_rating: float | None = Field(default=None, ge=0.0, le=5.0, allow_inf_nan=False)
    include_accessories: bool = False
    language: Literal["ar", "en"] = "ar"

    @field_validator("query")
    @classmethod
    def _validate_query(cls, value: str) -> str:
        if _has_control_or_bidi_chars(value):
            raise ValueError("query must not contain control or bidi characters")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query must not be blank")
        return cleaned


class SearchResponse(BaseModel):
    """Deterministic Top-3 search response preserving catalog provenance and cache hit."""

    model_config = ConfigDict(extra="forbid")

    intent: SearchIntent
    ranking_result: RankingResult
    source_mode: CatalogSourceMode
    cache_hit: bool
    latency_ms: float = Field(ge=0.0, allow_inf_nan=False)
    request_id: str


class MarketStoreSchema(BaseModel):
    """Supported regional marketplace store metadata for UI selectors."""

    model_config = ConfigDict(extra="forbid")

    store_id: StoreId
    label_en: str
    label_ar: str
    primary_domain: str


class MarketInfoSchema(BaseModel):
    """Regional market definition pairing currency, geolocation, and stores."""

    model_config = ConfigDict(extra="forbid")

    country: CountryCode
    currency: CurrencyCode
    name_en: str
    name_ar: str
    currency_label_en: str
    currency_label_ar: str
    serper_gl: str
    stores: list[MarketStoreSchema]


class MarketsResponse(BaseModel):
    """Catalog of supported regional markets and defaults."""

    model_config = ConfigDict(extra="forbid")

    markets: list[MarketInfoSchema]
    default_country: CountryCode = CountryCode.EG
    default_store: StoreFilter = StoreFilter.BOTH
    request_id: str


class HealthResponse(BaseModel):
    """Secret-free operational readiness and degradation status."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    app_env: str
    catalog_mode: str
    llm_mode: str
    cache_backend: str
    session_backend: str
    version: str


class ErrorResponse(BaseModel):
    """Unified sanitized error envelope across validation, rate limit, and outages."""

    model_config = ConfigDict(extra="forbid")

    error_code: str
    message: str
    retriable: bool = False
    request_id: str
    details: list[dict[str, Any]] | None = None
