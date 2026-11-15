"""Unit tests for hexagonal domain ports and bilingual regional SeedCatalogProvider."""

import ast
import inspect
from decimal import Decimal
from pathlib import Path

from commerce_ai.adapters.catalog.seed_provider import SeedCatalogProvider
from commerce_ai.config.markets import MARKET_REGISTRY, validate_regional_offer_url
from commerce_ai.domain import ports
from commerce_ai.domain.models import (
    CatalogSourceMode,
    CountryCode,
    ProductOffer,
    SearchIntent,
    StoreFilter,
    StoreId,
)
from commerce_ai.domain.ports import CacheStore, CatalogProvider

BACKEND_DIR = Path(__file__).resolve().parents[2]
PORTS_PATH = BACKEND_DIR / "src" / "commerce_ai" / "domain" / "ports.py"

ACCESSORY_MARKERS = (
    "case",
    "strap",
    "protector",
    "charger",
    "cable",
    "جراب",
    "كفر",
    "حافظة",
    "اسكرينة",
    "حماية شاشة",
    "شاحن",
    "كابل",
    "سوار",
)


def test_ports_have_no_vendor_imports() -> None:
    """T1.1 — domain/ports.py exposes exact async Protocols with zero vendor imports."""
    tree = ast.parse(PORTS_PATH.read_text(encoding="utf-8"), filename=str(PORTS_PATH))
    allowed_top_modules = {"typing", "commerce_ai"}
    forbidden_substrings = ("adapters", "httpx", "redis", "fakeredis", "serper", "langfuse")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_mod = alias.name.split(".")[0]
                assert top_mod in allowed_top_modules
                assert not any(bad in alias.name for bad in forbidden_substrings)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_mod = node.module.split(".")[0]
            assert top_mod in allowed_top_modules
            assert not any(bad in node.module for bad in forbidden_substrings)

    assert hasattr(ports, "CatalogProvider")
    assert hasattr(ports, "CacheStore")
    assert inspect.iscoroutinefunction(CatalogProvider.search_offers)
    assert inspect.iscoroutinefunction(CacheStore.get)
    assert inspect.iscoroutinefunction(CacheStore.set)
    assert inspect.iscoroutinefunction(CacheStore.delete)

    search_sig = inspect.signature(CatalogProvider.search_offers)
    assert list(search_sig.parameters.keys()) == ["self", "intent"]
    assert list(inspect.signature(CacheStore.get).parameters.keys()) == ["self", "key"]
    assert list(inspect.signature(CacheStore.set).parameters.keys()) == [
        "self",
        "key",
        "value",
        "ttl_seconds",
    ]
    assert list(inspect.signature(CacheStore.delete).parameters.keys()) == ["self", "key"]


def test_seed_datasets_cover_markets_categories_and_traps() -> None:
    """T1.5 — EG/SA/AE seeds span >=5 categories across Noon/Amazon and embed all 4 traps."""
    provider = SeedCatalogProvider()
    assert isinstance(provider, CatalogProvider)

    for country in (CountryCode.EG, CountryCode.SA, CountryCode.AE):
        items = provider.get_seed_items(country)
        assert len(items) >= 15

        categories = {item.category for item in items}
        stores = {item.offer.store for item in items}
        assert len(categories) >= 5
        assert stores == {StoreId.NOON, StoreId.AMAZON}

        expected_currency = MARKET_REGISTRY[country].currency
        for item in items:
            offer = item.offer
            assert isinstance(offer, ProductOffer)
            assert offer.country == country
            assert offer.currency == expected_currency
            validate_regional_offer_url(str(offer.url), country=country, store=offer.store)

        # Verify all 4 deliberate ranking traps exist in every market.
        has_accessory_trap = any(
            any(marker in item.offer.title.lower() for marker in ACCESSORY_MARKERS)
            for item in items
        )
        has_five_star_one_review_trap = any(
            item.offer.rating == 5.0 and item.offer.review_count == 1 for item in items
        )
        has_unrated_trap = any(
            item.offer.rating is None and item.offer.review_count == 0 for item in items
        )

        # Verify >= 4x scalper outlier within a category compared to normal primary products.
        earbud_prices = sorted(
            item.offer.price for item in items if item.category == "earbuds_audio"
        )
        normal_median = earbud_prices[len(earbud_prices) // 2]
        has_scalper_outlier = max(earbud_prices) >= Decimal("4") * normal_median

        assert has_accessory_trap
        assert has_five_star_one_review_trap
        assert has_unrated_trap
        assert has_scalper_outlier


async def test_seed_provider_bilingual_query_and_store_filter() -> None:
    """T1.6 — SeedCatalogProvider matches bilingual queries, filters stores, and keeps traps."""
    provider = SeedCatalogProvider()

    for country in (CountryCode.EG, CountryCode.SA, CountryCode.AE):
        ar_both = await provider.search_offers(
            SearchIntent(query="سماعة بلوتوث أنكر", country=country, store=StoreFilter.BOTH)
        )
        en_both = await provider.search_offers(
            SearchIntent(query="Anker earbuds", country=country, store=StoreFilter.BOTH)
        )

        assert ar_both.source_mode == CatalogSourceMode.SEED
        assert ar_both.cache_hit is False
        assert en_both.source_mode == CatalogSourceMode.SEED
        assert en_both.cache_hit is False

        ar_ids = {o.offer_id for o in ar_both.offers}
        en_ids = {o.offer_id for o in en_both.offers}
        assert len(ar_ids) >= 6
        assert ar_ids == en_ids
        assert {o.store for o in ar_both.offers} == {StoreId.NOON, StoreId.AMAZON}
        assert all(o.country == country for o in ar_both.offers)

        # Trap candidates matching the query remain intact for Feature 1.2 ranking.
        assert any(o.rating == 5.0 and o.review_count == 1 for o in ar_both.offers)
        assert any(o.rating is None and o.review_count == 0 for o in ar_both.offers)
        assert any(
            marker in o.title.lower()
            for o in ar_both.offers
            for marker in ("case", "جراب", "كفر", "حافظة")
        )

        noon_only = await provider.search_offers(
            SearchIntent(query="Anker earbuds", country=country, store=StoreFilter.NOON)
        )
        amazon_only = await provider.search_offers(
            SearchIntent(query="Anker earbuds", country=country, store=StoreFilter.AMAZON)
        )
        assert noon_only.offers and all(o.store == StoreId.NOON for o in noon_only.offers)
        assert amazon_only.offers and all(o.store == StoreId.AMAZON for o in amazon_only.offers)
        assert {o.offer_id for o in noon_only.offers} | {
            o.offer_id for o in amazon_only.offers
        } == ar_ids


async def test_seed_provider_arabic_variants_and_empty_match() -> None:
    """T3.9 — SeedCatalogProvider handles Arabic variants and empty match results."""
    provider = SeedCatalogProvider()

    nonexistent = await provider.search_offers(
        SearchIntent(query="xyz-nonexistent-999", country=CountryCode.EG)
    )
    assert nonexistent.source_mode == CatalogSourceMode.SEED
    assert nonexistent.cache_hit is False
    assert nonexistent.offers == []

    iphone_res = await provider.search_offers(
        SearchIntent(query="ايفون 15", country=CountryCode.EG)
    )
    assert len(iphone_res.offers) >= 2
    assert any("iPhone 15" in o.title for o in iphone_res.offers)

    earbuds_res = await provider.search_offers(
        SearchIntent(query="سماعه بلوتوث", country=CountryCode.SA)
    )
    assert len(earbuds_res.offers) >= 5
    assert all(o.country == CountryCode.SA for o in earbuds_res.offers)
