"""Single-call asynchronous Serper.dev Shopping catalog adapter."""

import hashlib
import logging
import math
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import HttpUrl, SecretStr, TypeAdapter, ValidationError

from commerce_ai.config.markets import (
    MARKET_REGISTRY,
    MarketConfig,
    has_control_or_whitespace,
    validate_regional_offer_url,
)
from commerce_ai.domain.errors import CatalogProviderError, OfferValidationError
from commerce_ai.domain.models import (
    CatalogSearchResult,
    CatalogSourceMode,
    CountryCode,
    CurrencyCode,
    ProductOffer,
    SearchIntent,
    StoreFilter,
    StoreId,
)

SERPER_SHOPPING_URL = "https://google.serper.dev/shopping"
_CENTS = Decimal("0.01")
_PRICE_NUMBER_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_ARABIC_DIGITS_TRANSLATION = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٬٫", "01234567890123456789,.")
_IMAGE_HTTP_URL_ADAPTER: TypeAdapter[HttpUrl] = TypeAdapter(HttpUrl)

_FOREIGN_CURRENCY_SYMBOLS = ("$", "€", "£", "¥", "₹", "₺")
_FOREIGN_CURRENCY_CODES_BY_EXPECTED: dict[CurrencyCode, tuple[str, ...]] = {
    CurrencyCode.EGP: ("usd", "eur", "gbp", "sar", "aed", "ر.س", "د.إ", "ريال", "درهم"),
    CurrencyCode.SAR: ("usd", "eur", "gbp", "egp", "aed", "ج.م", "د.إ", "جنيه", "درهم"),
    CurrencyCode.AED: ("usd", "eur", "gbp", "egp", "sar", "ج.م", "ر.س", "جنيه", "ريال"),
}
_LATIN_CODE_RE = re.compile(r"[a-z]{3}")

logger = logging.getLogger(__name__)


def _has_foreign_currency_marker(price_text: str, expected_currency: CurrencyCode) -> bool:
    if any(symbol in price_text for symbol in _FOREIGN_CURRENCY_SYMBOLS):
        return True
    lowered = price_text.lower()
    latin_tokens = set(_LATIN_CODE_RE.findall(lowered))
    for marker in _FOREIGN_CURRENCY_CODES_BY_EXPECTED[expected_currency]:
        if marker.isascii():
            if marker in latin_tokens:
                return True
        elif marker in lowered:
            return True
    return False


def _parse_price_decimal(raw_price: Any, expected_currency: CurrencyCode) -> Decimal | None:
    """Parse regional price values into quantized positive Decimal, or None if invalid."""
    if raw_price is None or isinstance(raw_price, bool):
        return None
    if isinstance(raw_price, (int, float, Decimal)):
        try:
            value = Decimal(str(raw_price))
        except InvalidOperation:
            return None
    elif isinstance(raw_price, str):
        cleaned = raw_price.strip().translate(_ARABIC_DIGITS_TRANSLATION)
        if not cleaned or _has_foreign_currency_marker(cleaned, expected_currency):
            return None
        matches = _PRICE_NUMBER_RE.findall(cleaned)
        if len(matches) != 1:
            return None
        try:
            value = Decimal(matches[0].replace(",", ""))
        except InvalidOperation:
            return None
    else:
        return None

    if not value.is_finite() or value <= Decimal("0"):
        return None
    quantized = value.quantize(_CENTS, rounding=ROUND_HALF_UP)
    return quantized if quantized > Decimal("0.00") else None


def _parse_rating(raw_rating: Any) -> float | None:
    if raw_rating is None or isinstance(raw_rating, bool):
        return None
    try:
        rating = float(raw_rating)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(rating) or rating < 0.0 or rating > 5.0:
        return None
    return rating


def _parse_review_count(raw_item: dict[str, Any]) -> int:
    raw_count = raw_item.get("ratingCount")
    if raw_count is None:
        raw_count = raw_item.get("reviewCount")
    if raw_count is None:
        raw_count = raw_item.get("reviews")
    if raw_count is None or isinstance(raw_count, bool):
        return 0
    if isinstance(raw_count, int):
        return max(0, raw_count)
    if isinstance(raw_count, str):
        digits = raw_count.strip().translate(_ARABIC_DIGITS_TRANSLATION).replace(",", "")
        if digits.isdigit():
            return int(digits)
    return 0


def _parse_https_image_url(raw_item: dict[str, Any]) -> str | None:
    raw_image = raw_item.get("imageUrl") or raw_item.get("image_url") or raw_item.get("thumbnail")
    if not isinstance(raw_image, str) or not raw_image:
        return None
    if has_control_or_whitespace(raw_image) or "\\" in raw_image:
        return None
    try:
        parsed = urlsplit(raw_image)
        _ = parsed.port
        _IMAGE_HTTP_URL_ADAPTER.validate_python(raw_image)
    except (ValueError, ValidationError):
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return raw_image


def _resolve_candidate_store(
    link: str,
    *,
    market: MarketConfig,
    merchant_attribution: str | None,
) -> StoreId | None:
    if not link or has_control_or_whitespace(link) or "\\" in link:
        return None
    try:
        parsed = urlsplit(link)
        _ = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() != "https":
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return None
    if host in market.amazon_domains:
        return StoreId.AMAZON
    if host in (market.noon_host, f"www.{market.noon_host}"):
        return StoreId.NOON
    if host in market.google_shopping_domains:
        if market.matches_merchant_attribution(StoreId.AMAZON, merchant_attribution):
            return StoreId.AMAZON
        if market.matches_merchant_attribution(StoreId.NOON, merchant_attribution):
            return StoreId.NOON
    return None


class SerperShoppingProvider:
    """CatalogProvider executing strictly 1 Serper.dev Shopping POST call per search."""

    def __init__(
        self,
        api_key: SecretStr,
        *,
        timeout_seconds: float = 2.0,
        client: httpx.AsyncClient | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.get_secret_value().strip():
            raise CatalogProviderError(
                provider="serper",
                retriable=False,
                reason="SERPER_API_KEY must not be empty",
            )
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client = http_client if http_client is not None else client

    def _redact_reason(self, message: str) -> str:
        secret = self._api_key.get_secret_value()
        if secret:
            return message.replace(secret, "***")
        return message

    async def _post_shopping(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {
            "X-API-KEY": self._api_key.get_secret_value(),
            "Content-Type": "application/json",
        }
        if self._client is not None:
            return await self._client.post(
                SERPER_SHOPPING_URL,
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            return await client.post(
                SERPER_SHOPPING_URL,
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )

    def _parse_item(
        self,
        raw_item: Any,
        *,
        country: CountryCode,
        store_filter: StoreFilter,
        market: MarketConfig,
        seen_offer_ids: set[str],
    ) -> ProductOffer | None:
        if not isinstance(raw_item, dict):
            return None

        raw_title = raw_item.get("title")
        raw_link = raw_item.get("link")
        if not isinstance(raw_title, str) or not raw_title.strip():
            return None
        if not isinstance(raw_link, str) or not raw_link.strip():
            return None

        raw_source = raw_item.get("source")
        merchant_attribution = raw_source.strip() if isinstance(raw_source, str) else None

        candidate_store = _resolve_candidate_store(
            raw_link,
            market=market,
            merchant_attribution=merchant_attribution,
        )
        if candidate_store is None:
            return None
        if store_filter == StoreFilter.NOON and candidate_store != StoreId.NOON:
            return None
        if store_filter == StoreFilter.AMAZON and candidate_store != StoreId.AMAZON:
            return None

        parsed_price = _parse_price_decimal(raw_item.get("price"), market.currency)
        if parsed_price is None:
            return None

        raw_product_id = raw_item.get("productId")
        if (
            isinstance(raw_product_id, (str, int))
            and not isinstance(raw_product_id, bool)
            and str(raw_product_id).strip()
        ):
            base_offer_id = f"serper-{candidate_store.value}-{str(raw_product_id).strip()}"
        else:
            digest = hashlib.sha256(f"{candidate_store.value}:{raw_link}".encode()).hexdigest()[:12]
            base_offer_id = f"serper-{candidate_store.value}-{digest}"

        offer_id = base_offer_id
        suffix = 2
        while offer_id in seen_offer_ids:
            offer_id = f"{base_offer_id}-{suffix}"
            suffix += 1

        try:
            validated_url = validate_regional_offer_url(
                raw_link,
                country=country,
                store=candidate_store,
                merchant_attribution=merchant_attribution,
            )
            offer = ProductOffer.model_validate(
                {
                    "offer_id": offer_id,
                    "title": raw_title.strip(),
                    "price": parsed_price,
                    "currency": market.currency,
                    "store": candidate_store,
                    "country": country,
                    "url": validated_url,
                    "rating": _parse_rating(raw_item.get("rating")),
                    "review_count": _parse_review_count(raw_item),
                    "image_url": _parse_https_image_url(raw_item),
                    "in_stock": True,
                },
                context={"merchant_attribution": merchant_attribution},
            )
        except (OfferValidationError, ValidationError, ValueError):
            return None

        seen_offer_ids.add(offer.offer_id)
        return offer

    async def search_offers(self, intent: SearchIntent) -> CatalogSearchResult:
        """Issue 1 Serper Shopping POST request and return validated regional offers."""
        market = MARKET_REGISTRY[intent.country]
        query = intent.query.strip()
        if intent.store == StoreFilter.NOON:
            query = f"{query} noon"
        elif intent.store == StoreFilter.AMAZON:
            query = f"{query} amazon"

        request_payload = {
            "q": query,
            "gl": market.serper_gl,
            "hl": intent.language,
            "num": 40,
        }

        try:
            response = await self._post_shopping(request_payload)
        except httpx.TimeoutException as exc:
            reason = self._redact_reason(f"Serper Shopping request timed out: {exc}")
            logger.warning("Serper timeout for country=%s: %s", intent.country.value, reason)
            raise CatalogProviderError(provider="serper", retriable=True, reason=reason) from exc
        except httpx.TransportError as exc:
            reason = self._redact_reason(f"Serper Shopping transport error: {exc}")
            logger.warning("Serper transport failure: %s", reason)
            raise CatalogProviderError(provider="serper", retriable=True, reason=reason) from exc
        except httpx.HTTPError as exc:
            reason = self._redact_reason(f"Serper Shopping HTTP error: {exc}")
            logger.warning("Serper HTTP failure: %s", reason)
            raise CatalogProviderError(provider="serper", retriable=False, reason=reason) from exc

        if response.status_code < 200 or response.status_code >= 300:
            retriable = response.status_code == 429 or 500 <= response.status_code < 600
            reason = f"Serper Shopping API returned HTTP {response.status_code}"
            logger.warning("%s (retriable=%s)", reason, retriable)
            raise CatalogProviderError(provider="serper", retriable=retriable, reason=reason)

        try:
            body: Any = response.json()
        except ValueError as exc:
            reason = "Serper Shopping API returned malformed JSON"
            logger.warning("%s", reason)
            raise CatalogProviderError(provider="serper", retriable=False, reason=reason) from exc

        if not isinstance(body, dict) or not isinstance(body.get("shopping"), list):
            reason = "Serper Shopping API response missing list 'shopping' field"
            logger.warning("%s", reason)
            raise CatalogProviderError(provider="serper", retriable=False, reason=reason)

        seen_offer_ids: set[str] = set()
        offers: list[ProductOffer] = []
        for raw_item in body["shopping"]:
            offer = self._parse_item(
                raw_item,
                country=intent.country,
                store_filter=intent.store,
                market=market,
                seen_offer_ids=seen_offer_ids,
            )
            if offer is not None:
                offers.append(offer)

        return CatalogSearchResult(
            offers=offers,
            source_mode=CatalogSourceMode.LIVE,
            cache_hit=False,
        )
