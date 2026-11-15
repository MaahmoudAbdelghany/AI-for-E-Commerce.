"""Pure marketplace domain enums and validated value/search/agent schemas."""

import hashlib
import re
import unicodedata
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    PrivateAttr,
    TypeAdapter,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic import ValidationError as PydanticValidationError

from commerce_ai.domain.errors import OfferValidationError

_CENTS = Decimal("0.01")
_HTTP_URL_ADAPTER: TypeAdapter[HttpUrl] = TypeAdapter(HttpUrl)


def _has_control_or_whitespace(value: str) -> bool:
    return any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)


def _validate_clean_url_input(value: Any, *, field_name: str) -> str:
    if isinstance(value, HttpUrl):
        raw = str(value)
    elif isinstance(value, str):
        raw = value
    else:
        raise OfferValidationError(f"{field_name} must be a string URL")
    if not raw:
        raise OfferValidationError(f"{field_name} must not be empty")
    if _has_control_or_whitespace(raw):
        raise OfferValidationError(
            f"{field_name} must not contain whitespace or control characters"
        )
    if "\\" in raw:
        raise OfferValidationError(f"{field_name} must not contain backslashes")
    try:
        _HTTP_URL_ADAPTER.validate_python(raw)
    except PydanticValidationError as exc:
        raise OfferValidationError(f"{field_name} must be a valid HTTP(S) URL") from exc
    return raw


_ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_ARABIC_ORTHOGRAPHY_TRANS = str.maketrans(
    {
        "\u0622": "\u0627",  # آ -> ا
        "\u0623": "\u0627",  # أ -> ا
        "\u0625": "\u0627",  # إ -> ا
        "\u0671": "\u0627",  # ٱ -> ا
        "\u0629": "\u0647",  # ة -> ه
        "\u0649": "\u064a",  # ى -> ي
    }
)
_NON_ALNUM_ARABIC_RE = re.compile(r"[^a-z0-9\u0621-\u064A\u0660-\u0669\u06F0-\u06F9]+")


class CountryCode(StrEnum):
    """Supported target regional markets."""

    EG = "EG"
    SA = "SA"
    AE = "AE"


class CurrencyCode(StrEnum):
    """Official currencies paired 1-to-1 with supported markets."""

    EGP = "EGP"
    SAR = "SAR"
    AED = "AED"


class StoreId(StrEnum):
    """Supported regional marketplace identifiers."""

    NOON = "noon"
    AMAZON = "amazon"


class StoreFilter(StrEnum):
    """Search store scope filter."""

    NOON = "noon"
    AMAZON = "amazon"
    BOTH = "both"


class CatalogSourceMode(StrEnum):
    """Provenance of returned catalog offers."""

    SEED = "seed"
    LIVE = "live"


class TurnAction(StrEnum):
    """Classified conversational action for a user turn."""

    SEARCH = "search"
    COMPARE = "compare"
    CLARIFY = "clarify"
    OFF_TOPIC = "off_topic"
    REFUSE = "refuse"


class TurnStatus(StrEnum):
    """Final execution status returned for a conversational turn."""

    OK = "ok"
    CLARIFY = "clarify"
    OFF_TOPIC = "off_topic"
    REFUSED = "refused"
    DEGRADED = "degraded"


def _validate_positive_currency_decimal(value: Decimal, *, field_name: str) -> Decimal:
    """Validate finiteness, positive sign, and 2-decimal currency quantization."""
    if not value.is_finite():
        raise OfferValidationError(f"{field_name} must be a finite Decimal")
    if value <= Decimal("0"):
        raise OfferValidationError(f"{field_name} must be greater than 0")
    quantized = value.quantize(_CENTS, rounding=ROUND_HALF_UP)
    if quantized <= Decimal("0.00"):
        raise OfferValidationError(f"{field_name} must remain greater than 0.00 after quantization")
    return quantized


def _require_non_empty_text(value: str, *, field_name: str) -> str:
    """Trim text and reject empty or whitespace-only values."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    return cleaned


class ProductOffer(BaseModel):
    """Verified marketplace offer grounded in a specific regional market and store."""

    model_config = ConfigDict(extra="forbid")

    offer_id: str
    title: str
    price: Decimal
    currency: CurrencyCode
    store: StoreId
    country: CountryCode
    url: str
    rating: float | None = Field(default=None, ge=0.0, le=5.0, allow_inf_nan=False)
    review_count: int = Field(default=0, ge=0)
    image_url: str | None = None
    in_stock: bool = True
    _google_attribution_verified: bool = PrivateAttr(default=False)

    @field_validator("offer_id")
    @classmethod
    def _validate_offer_id(cls, value: str) -> str:
        return _require_non_empty_text(value, field_name="offer_id")

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _require_non_empty_text(value, field_name="title")

    @field_validator("price")
    @classmethod
    def _validate_price(cls, value: Decimal) -> Decimal:
        return _validate_positive_currency_decimal(value, field_name="price")

    @field_validator("url", mode="before")
    @classmethod
    def _validate_url_syntax(cls, value: Any) -> str:
        return _validate_clean_url_input(value, field_name="url")

    @field_validator("image_url", mode="before")
    @classmethod
    def _validate_image_url(cls, value: Any) -> str | None:
        if value is None:
            return None
        raw = _validate_clean_url_input(value, field_name="image_url")
        try:
            parsed = urlsplit(raw)
            _ = parsed.port
        except ValueError as exc:
            raise OfferValidationError("image_url must be a valid https:// URL") from exc
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise OfferValidationError("image_url must be a valid https:// URL")
        if parsed.username is not None or parsed.password is not None:
            raise OfferValidationError("image_url must not contain embedded credentials")
        return raw

    @model_validator(mode="after")
    def _validate_market_and_url(self, info: ValidationInfo) -> Self:
        # Local import prevents a top-level import cycle with commerce_ai.config.markets.
        from commerce_ai.config.markets import MARKET_REGISTRY, _validate_regional_offer_url

        market = MARKET_REGISTRY[self.country]
        if self.currency != market.currency:
            raise OfferValidationError(
                f"Currency {self.currency.value} does not match country "
                f"{self.country.value} (expected {market.currency.value})"
            )

        context = info.context
        has_attribution_key = isinstance(context, Mapping) and "merchant_attribution" in context
        raw_attribution = (
            context.get("merchant_attribution") if isinstance(context, Mapping) else None
        )
        if raw_attribution is not None and not isinstance(raw_attribution, str):
            raise OfferValidationError("merchant_attribution context value must be a string")

        allow_cached_google = (
            isinstance(context, Mapping)
            and context.get("allow_verified_google_shopping_from_cache") is True
            and not has_attribution_key
        )
        # Never bypass attribution on arbitrary JSON payloads; only allow verified in-memory
        # offers (e.g. wrapped in RankedOffer) or explicit trusted cache deserialization.
        require_attribution = has_attribution_key or (
            not self._google_attribution_verified and not allow_cached_google
        )
        self.url = _validate_regional_offer_url(
            self.url,
            country=self.country,
            store=self.store,
            merchant_attribution=raw_attribution,
            require_attribution_for_google=require_attribution,
        )
        self._google_attribution_verified = True
        return self


class SearchIntent(BaseModel):
    """Normalized shopper search query and constraints."""

    model_config = ConfigDict(extra="forbid")

    query: str
    country: CountryCode
    store: StoreFilter = StoreFilter.BOTH
    max_budget: Decimal | None = None
    min_rating: float | None = Field(default=None, ge=0.0, le=5.0, allow_inf_nan=False)
    exclude_keywords: tuple[str, ...] = ()
    include_accessories: bool = False
    language: Literal["ar", "en"] = "ar"

    @field_validator("query")
    @classmethod
    def _validate_query(cls, value: str) -> str:
        return _require_non_empty_text(value, field_name="query")

    @field_validator("max_budget")
    @classmethod
    def _validate_max_budget(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return _validate_positive_currency_decimal(value, field_name="max_budget")

    def _query_slug(self) -> str:
        normalized = unicodedata.normalize("NFKC", self.query).lower()
        without_diacritics = _ARABIC_DIACRITICS_RE.sub("", normalized)
        folded = without_diacritics.translate(_ARABIC_ORTHOGRAPHY_TRANS)
        slug = _NON_ALNUM_ARABIC_RE.sub("-", folded).strip("-")
        if not slug:
            digest = hashlib.sha256(self.query.strip().encode("utf-8")).hexdigest()[:8]
            return f"q-{digest}"
        return slug

    def catalog_cache_key(self) -> str:
        """Return canonical lowercase '{country}:{store}:{language}:{slug}' catalog cache key."""
        return (
            f"{self.country.value.lower()}:{self.store.value.lower()}:"
            f"{self.language.lower()}:{self._query_slug()}"
        )

    def normalized_cache_key(self) -> str:
        """Return canonical '{country}:{store}:{language}:{slug}:{budget}:{min_rating}' key."""
        budget_part = f"{self.max_budget:.2f}" if self.max_budget is not None else "none"
        rating_part = f"{self.min_rating:.2f}" if self.min_rating is not None else "none"
        return f"{self.catalog_cache_key()}:{budget_part}:{rating_part}"


class RankedOffer(BaseModel):
    """Single scored offer in the Top-K recommendation output."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1, le=3)
    offer: ProductOffer
    value_score: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    price_norm: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    bayesian_rating: float = Field(ge=0.0, le=5.0, allow_inf_nan=False)
    match_reasons: tuple[str, ...] = ()


class RankingResult(BaseModel):
    """Complete deterministic ranking result including filter counts and degradation status."""

    model_config = ConfigDict(extra="forbid")

    ranked_offers: list[RankedOffer]
    total_candidates: int = Field(ge=0)
    filtered_accessories_count: int = Field(ge=0)
    filtered_outliers_count: int = Field(ge=0)
    degraded_fewer_than_k: bool


class CatalogSearchResult(BaseModel):
    """Catalog search response carrying provenance and cache metadata."""

    model_config = ConfigDict(extra="forbid")

    offers: list[ProductOffer]
    source_mode: CatalogSourceMode
    cache_hit: bool = False


class LLMMessage(BaseModel):
    """Single role-tagged message passed to an LLM completion port."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    """Bounded completion request dispatched to an LLMClient adapter."""

    model_config = ConfigDict(extra="forbid")

    messages: tuple[LLMMessage, ...] = Field(min_length=1)
    max_tokens: int = Field(default=350, ge=1, le=1024)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
    json_mode: bool = False
    json_schema: dict[str, Any] | None = None
    task_name: str = "general"


class LLMResponse(BaseModel):
    """Completion output and usage telemetry returned by an LLMClient adapter."""

    model_config = ConfigDict(extra="forbid")

    content: str
    provider: str
    model: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    used_fallback_model: bool = False


class SessionTurn(BaseModel):
    """Compact conversational turn stored in session memory."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str
    action: TurnAction | None = None
    created_at_iso: str


class SessionState(BaseModel):
    """Persisted multi-turn shopping session state."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    market: CountryCode = CountryCode.EG
    last_intent: SearchIntent | None = None
    last_ranked_offers: list[RankedOffer] = Field(default_factory=list)
    turns: list[SessionTurn] = Field(default_factory=list)
    updated_at_epoch: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        return _require_non_empty_text(value, field_name="session_id")


class TurnTelemetry(BaseModel):
    """Execution cost, cache, fallback, and latency telemetry for a single turn."""

    model_config = ConfigDict(extra="forbid")

    llm_calls: int = Field(default=0, ge=0, le=2)
    catalog_called: bool = False
    catalog_cache_hit: bool = False
    catalog_source_mode: CatalogSourceMode | None = None
    used_rule_intent_fallback: bool = False
    used_template_summary: bool = False
    degraded_reason: str | None = None
    latency_ms: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)


class ChatTurnResult(BaseModel):
    """Complete workflow response for a single conversational shopping turn."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: TurnStatus
    reply: str
    action: TurnAction
    active_intent: SearchIntent | None = None
    top_offers: list[RankedOffer] = Field(default_factory=list)
    ranking_result: RankingResult | None = None
    telemetry: TurnTelemetry

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        return _require_non_empty_text(value, field_name="session_id")
