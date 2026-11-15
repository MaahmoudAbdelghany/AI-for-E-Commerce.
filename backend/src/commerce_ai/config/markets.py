"""Regional market definitions and strict store URL / merchant attribution rules."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import unquote, urlsplit

from commerce_ai.domain.errors import OfferValidationError
from commerce_ai.domain.models import CountryCode, CurrencyCode, StoreId


def _normalize_merchant_label(label: str) -> str:
    """Normalize merchant attribution labels while preserving host dots."""
    collapsed = re.sub(r"[\s\-_()/]+", " ", label.strip().lower())
    return " ".join(collapsed.split())


@dataclass(frozen=True, slots=True)
class MarketConfig:
    """Regional market rules for currency, Serper geolocation, and verified store links."""

    country: CountryCode
    currency: CurrencyCode
    serper_gl: str
    amazon_domains: tuple[str, ...]
    noon_host: str
    noon_path_prefixes: tuple[str, ...]
    google_shopping_domains: tuple[str, ...]
    amazon_merchant_attributions: tuple[str, ...]
    noon_merchant_attributions: tuple[str, ...]

    def matches_merchant_attribution(
        self,
        store: StoreId,
        merchant_attribution: str | None,
    ) -> bool:
        """Return True iff merchant_attribution explicitly identifies the regional store."""
        if merchant_attribution is None:
            return False
        normalized = _normalize_merchant_label(merchant_attribution)
        if not normalized:
            return False
        allowed = (
            self.amazon_merchant_attributions
            if store == StoreId.AMAZON
            else self.noon_merchant_attributions
        )
        return normalized in allowed


MARKET_REGISTRY: Mapping[CountryCode, MarketConfig] = MappingProxyType(
    {
        CountryCode.EG: MarketConfig(
            country=CountryCode.EG,
            currency=CurrencyCode.EGP,
            serper_gl="eg",
            amazon_domains=("amazon.eg", "www.amazon.eg"),
            noon_host="noon.com",
            noon_path_prefixes=("/egypt",),
            google_shopping_domains=(
                "google.com",
                "www.google.com",
                "google.com.eg",
                "www.google.com.eg",
            ),
            amazon_merchant_attributions=(
                "amazon.eg",
                "www.amazon.eg",
                "amazon eg",
                "amazon egypt",
                "amazon.com.eg",
                "أمازون مصر",
                "امازون مصر",
            ),
            noon_merchant_attributions=(
                "noon",
                "noon.com",
                "www.noon.com",
                "noon eg",
                "noon egypt",
                "noon.com egypt",
                "نون",
                "نون مصر",
            ),
        ),
        CountryCode.SA: MarketConfig(
            country=CountryCode.SA,
            currency=CurrencyCode.SAR,
            serper_gl="sa",
            amazon_domains=("amazon.sa", "www.amazon.sa"),
            noon_host="noon.com",
            noon_path_prefixes=("/saudi",),
            google_shopping_domains=(
                "google.com",
                "www.google.com",
                "google.com.sa",
                "www.google.com.sa",
            ),
            amazon_merchant_attributions=(
                "amazon.sa",
                "www.amazon.sa",
                "amazon sa",
                "amazon saudi",
                "amazon saudi arabia",
                "amazon ksa",
                "أمازون السعودية",
                "امازون السعودية",
            ),
            noon_merchant_attributions=(
                "noon",
                "noon.com",
                "www.noon.com",
                "noon sa",
                "noon saudi",
                "noon saudi arabia",
                "noon ksa",
                "noon.com saudi",
                "نون",
                "نون السعودية",
            ),
        ),
        CountryCode.AE: MarketConfig(
            country=CountryCode.AE,
            currency=CurrencyCode.AED,
            serper_gl="ae",
            amazon_domains=("amazon.ae", "www.amazon.ae"),
            noon_host="noon.com",
            noon_path_prefixes=("/uae",),
            google_shopping_domains=(
                "google.com",
                "www.google.com",
                "google.ae",
                "www.google.ae",
            ),
            amazon_merchant_attributions=(
                "amazon.ae",
                "www.amazon.ae",
                "amazon ae",
                "amazon uae",
                "amazon emirates",
                "amazon united arab emirates",
                "أمازون الإمارات",
                "امازون الامارات",
            ),
            noon_merchant_attributions=(
                "noon",
                "noon.com",
                "www.noon.com",
                "noon ae",
                "noon uae",
                "noon emirates",
                "noon dubai",
                "noon.com uae",
                "نون",
                "نون الإمارات",
            ),
        ),
    }
)


def has_control_or_whitespace(value: str) -> bool:
    """Return True if value contains whitespace or ASCII control characters."""
    return any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)


def _normalize_and_validate_path_segments(raw_path: str) -> tuple[str, ...]:
    """Reject path-confusion payloads and return lowercased normalized segments."""
    if ";" in raw_path or "\\" in raw_path:
        raise OfferValidationError("Offer URL path contains disallowed characters")
    lower_raw = raw_path.lower()
    if "%2f" in lower_raw or "%5c" in lower_raw or "%3b" in lower_raw:
        raise OfferValidationError("Offer URL path must not contain encoded delimiters")

    segments: list[str] = []
    for raw_seg in raw_path.split("/"):
        if raw_seg == "":
            continue
        once = unquote(raw_seg)
        twice = unquote(once)
        for candidate in (raw_seg, once, twice):
            if candidate in {".", ".."}:
                raise OfferValidationError("Offer URL path must not contain traversal segments")
            if any(ord(ch) < 0x20 or ord(ch) == 0x7F or ch in "/\\;" for ch in candidate):
                raise OfferValidationError("Offer URL path contains disallowed characters")
        segments.append(once.lower())
    return tuple(segments)


def _matches_noon_path(segments: tuple[str, ...], prefixes: tuple[str, ...]) -> bool:
    if not segments:
        return False
    first_segment = segments[0]
    for prefix in prefixes:
        clean_prefix = prefix.lstrip("/").lower()
        if first_segment == clean_prefix or (
            first_segment.startswith(f"{clean_prefix}-")
            and len(first_segment) > len(clean_prefix) + 1
        ):
            return True
    return False


def _validate_regional_offer_url(
    url: str,
    *,
    country: CountryCode,
    store: StoreId,
    merchant_attribution: str | None = None,
    require_attribution_for_google: bool = True,
) -> str:
    """Internal URL validator supporting optional Google attribution skip on JSON reload."""
    if not url:
        raise OfferValidationError("Offer URL must not be empty")
    if has_control_or_whitespace(url):
        raise OfferValidationError("Offer URL must not contain whitespace or control characters")
    if "\\" in url:
        raise OfferValidationError("Offer URL must not contain backslashes")

    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError as exc:
        raise OfferValidationError("Offer URL is malformed") from exc

    if parsed.scheme.lower() != "https":
        raise OfferValidationError(f"Offer URL must use https:// (got {parsed.scheme!r})")
    if parsed.username is not None or parsed.password is not None:
        raise OfferValidationError("Offer URL must not contain embedded credentials")

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise OfferValidationError("Offer URL must include a valid hostname")

    market = MARKET_REGISTRY.get(country)
    if market is None:
        raise OfferValidationError(f"Unsupported country code: {country!r}")

    segments = _normalize_and_validate_path_segments(parsed.path)

    if store == StoreId.AMAZON and host in market.amazon_domains:
        return url

    noon_hosts = (market.noon_host, f"www.{market.noon_host}")
    if (
        store == StoreId.NOON
        and host in noon_hosts
        and _matches_noon_path(segments, market.noon_path_prefixes)
    ):
        return url

    if host in market.google_shopping_domains:
        if not segments or segments[0] != "shopping":
            raise OfferValidationError(
                f"Google URL {url!r} must target /shopping/... rather than non-shopping paths"
            )
        if require_attribution_for_google and not market.matches_merchant_attribution(
            store, merchant_attribution
        ):
            raise OfferValidationError(
                f"Google Shopping URL for {country.value}/{store.value} requires matching "
                f"regional merchant attribution (got {merchant_attribution!r})"
            )
        return url

    raise OfferValidationError(
        f"Offer URL host {host!r} is not an authorized {store.value} or Google Shopping "
        f"endpoint for market {country.value}"
    )


def validate_regional_offer_url(
    url: str,
    *,
    country: CountryCode,
    store: StoreId,
    merchant_attribution: str | None = None,
) -> str:
    """Validate an HTTPS regional Noon/Amazon or attributed Google Shopping offer URL."""
    return _validate_regional_offer_url(
        url,
        country=country,
        store=store,
        merchant_attribution=merchant_attribution,
        require_attribution_for_google=True,
    )
