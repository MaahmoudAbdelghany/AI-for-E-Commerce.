"""Offline deterministic seed catalog adapter with bilingual Arabic/English matching."""

import re
import unicodedata
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from commerce_ai.config.markets import MARKET_REGISTRY
from commerce_ai.domain.errors import CatalogProviderError
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

_DEFAULT_SEEDS_DIR = Path(__file__).resolve().parent / "seeds"
_ARABIC_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "for",
        "with",
        "in",
        "on",
        "of",
        "to",
        "and",
        "or",
        "من",
        "في",
        "على",
        "مع",
        "عن",
        "إلى",
        "الى",
        "و",
        "أو",
        "او",
        "ل",
    }
)


def normalize_bilingual_text(text: str) -> str:
    """Normalize Arabic and English text for deterministic query matching."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = _ARABIC_DIACRITICS_RE.sub("", normalized)
    normalized = (
        normalized.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ة", "ه")
        .replace("ى", "ي")
    )
    normalized = _NON_WORD_RE.sub(" ", normalized)
    return " ".join(normalized.split())


def _token_forms(token: str) -> set[str]:
    forms = {token}
    if token.startswith("ال") and len(token) > 3:
        forms.add(token[2:])
    if token.isascii() and token.endswith("s") and len(token) > 3:
        forms.add(token[:-1])
    return forms


class SeedCatalogItem(BaseModel):
    """Validated seed catalog entry pairing metadata/keywords with a grounded ProductOffer."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    keywords: tuple[str, ...] = Field(min_length=1)
    offer: ProductOffer


class SeedCatalogFile(BaseModel):
    """Validated per-country versioned seed dataset schema."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    country: CountryCode
    currency: CurrencyCode
    items: tuple[SeedCatalogItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_market_consistency(self) -> "SeedCatalogFile":
        expected_currency = MARKET_REGISTRY[self.country].currency
        if self.currency != expected_currency:
            raise ValueError(
                f"Seed currency {self.currency.value} does not match {self.country.value}"
            )
        for item in self.items:
            if item.offer.country != self.country:
                raise ValueError(
                    f"Seed offer {item.offer.offer_id} country {item.offer.country.value} "
                    f"does not match file country {self.country.value}"
                )
        return self


class _IndexedSeedItem:
    """Pre-normalized seed entry for fast deterministic matching."""

    __slots__ = ("item", "haystack", "tokens")

    def __init__(self, item: SeedCatalogItem) -> None:
        self.item = item
        combined = " ".join(
            [
                item.offer.title,
                item.brand,
                item.category.replace("_", " "),
                *item.keywords,
            ]
        )
        self.haystack = normalize_bilingual_text(combined)
        tokens: set[str] = set()
        for tok in self.haystack.split():
            tokens.update(_token_forms(tok))
        self.tokens = tokens

    def matches_query(self, query_tokens: list[str]) -> bool:
        if not query_tokens:
            return False
        for q_tok in query_tokens:
            forms = _token_forms(q_tok)
            if forms & self.tokens:
                continue
            if len(q_tok) >= 3 and any(form in self.haystack for form in forms):
                continue
            return False
        return True


class SeedCatalogProvider:
    """Offline CatalogProvider backed by curated bilingual EG/SA/AE JSON fixtures."""

    def __init__(self, seeds_dir: Path | None = None) -> None:
        self._seeds_dir = seeds_dir if seeds_dir is not None else _DEFAULT_SEEDS_DIR
        self._datasets: dict[CountryCode, SeedCatalogFile] = {}
        self._indexed: dict[CountryCode, tuple[_IndexedSeedItem, ...]] = {}
        self._load_all_markets()

    def _load_all_markets(self) -> None:
        for country in CountryCode:
            seed_path = self._seeds_dir / f"{country.value.lower()}.json"
            try:
                raw_text = seed_path.read_text(encoding="utf-8")
                dataset = SeedCatalogFile.model_validate_json(raw_text)
            except (OSError, ValueError) as exc:
                raise CatalogProviderError(
                    provider="seed",
                    retriable=False,
                    reason=f"Failed to load seed catalog for {country.value}: {exc}",
                ) from exc
            if dataset.country != country:
                raise CatalogProviderError(
                    provider="seed",
                    retriable=False,
                    reason=(
                        f"Seed file {seed_path.name} declared country {dataset.country.value} "
                        f"instead of {country.value}"
                    ),
                )
            self._datasets[country] = dataset
            self._indexed[country] = tuple(_IndexedSeedItem(item) for item in dataset.items)

    def get_seed_items(self, country: CountryCode) -> tuple[SeedCatalogItem, ...]:
        """Return validated seed items for a regional market."""
        return self._datasets[country].items

    async def search_offers(self, intent: SearchIntent) -> CatalogSearchResult:
        """Match normalized Arabic/English query tokens and filter by country/store."""
        normalized_query = normalize_bilingual_text(intent.query)
        raw_tokens = normalized_query.split()
        query_tokens = [tok for tok in raw_tokens if tok not in _STOP_WORDS]
        if not query_tokens:
            query_tokens = raw_tokens

        target_store: StoreId | None = None
        if intent.store == StoreFilter.NOON:
            target_store = StoreId.NOON
        elif intent.store == StoreFilter.AMAZON:
            target_store = StoreId.AMAZON

        matched_offers: list[ProductOffer] = []
        for entry in self._indexed[intent.country]:
            offer = entry.item.offer
            if target_store is not None and offer.store != target_store:
                continue
            if entry.matches_query(query_tokens):
                matched_offers.append(offer)

        return CatalogSearchResult(
            offers=matched_offers,
            source_mode=CatalogSourceMode.SEED,
            cache_hit=False,
        )
