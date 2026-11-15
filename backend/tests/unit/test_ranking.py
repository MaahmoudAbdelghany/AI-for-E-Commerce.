"""Offline deterministic unit & edge-case tests for Feature 1.2 ranking engine."""

import ast
import socket
import sys
import time
from decimal import Decimal
from pathlib import Path

import pytest

from commerce_ai.config import ScoringConfig
from commerce_ai.domain.models import (
    CountryCode,
    CurrencyCode,
    ProductOffer,
    SearchIntent,
    StoreFilter,
    StoreId,
)
from commerce_ai.domain.ranking import rank_top_offers

BACKEND_DIR = Path(__file__).resolve().parents[2]
RANKING_MODULE_PATH = BACKEND_DIR / "src" / "commerce_ai" / "domain" / "ranking.py"

_CURRENCY_BY_COUNTRY = {
    CountryCode.EG: CurrencyCode.EGP,
    CountryCode.SA: CurrencyCode.SAR,
    CountryCode.AE: CurrencyCode.AED,
}


def _make_offer(
    offer_id: str,
    *,
    title: str = "Anker Soundcore Liberty 4 NC",
    price: str | Decimal = "1500.00",
    store: StoreId = StoreId.AMAZON,
    country: CountryCode = CountryCode.EG,
    rating: float | None = 4.6,
    review_count: int = 100,
    in_stock: bool = True,
) -> ProductOffer:
    currency = _CURRENCY_BY_COUNTRY[country]
    if store == StoreId.AMAZON:
        domain = {
            CountryCode.EG: "amazon.eg",
            CountryCode.SA: "amazon.sa",
            CountryCode.AE: "amazon.ae",
        }[country]
        url = f"https://www.{domain}/dp/{offer_id}"
    else:
        prefix = {
            CountryCode.EG: "egypt-en",
            CountryCode.SA: "saudi-en",
            CountryCode.AE: "uae-en",
        }[country]
        url = f"https://www.noon.com/{prefix}/{offer_id}"

    return ProductOffer(
        offer_id=offer_id,
        title=title,
        price=Decimal(price) if not isinstance(price, Decimal) else price,
        currency=currency,
        store=store,
        country=country,
        url=url,
        rating=rating,
        review_count=review_count,
        in_stock=in_stock,
    )


def test_balanced_top_3_ranking_and_determinism() -> None:
    """T1.1 — Balanced Top-3 value ranking, exact math, and bit-identical determinism."""
    offers = [
        _make_offer(
            "o5",
            title="Sony Earbuds Model E",
            price="2000.00",
            store=StoreId.NOON,
            rating=4.2,
            review_count=50,
        ),
        _make_offer(
            "o2",
            title="Sony Earbuds Model B",
            price="1200.00",
            store=StoreId.AMAZON,
            rating=4.9,
            review_count=400,
        ),
        _make_offer(
            "o1",
            title="Sony Earbuds Model A",
            price="1000.00",
            store=StoreId.NOON,
            rating=4.6,
            review_count=100,
        ),
        _make_offer(
            "o4",
            title="Sony Earbuds Model D",
            price="1600.00",
            store=StoreId.AMAZON,
            rating=4.5,
            review_count=80,
        ),
        _make_offer(
            "o3",
            title="Sony Earbuds Model C",
            price="1400.00",
            store=StoreId.NOON,
            rating=4.8,
            review_count=200,
        ),
    ]
    intent = SearchIntent(query="Sony Earbuds", country=CountryCode.EG)

    result_first = rank_top_offers(offers, intent)
    result_second = rank_top_offers(offers, intent)

    assert result_first == result_second
    assert result_first.total_candidates == 5
    assert result_first.filtered_accessories_count == 0
    assert result_first.filtered_outliers_count == 0
    assert result_first.degraded_fewer_than_k is False
    assert [item.rank for item in result_first.ranked_offers] == [1, 2, 3]
    assert [item.offer.offer_id for item in result_first.ranked_offers] == ["o1", "o2", "o3"]

    r1, r2, r3 = result_first.ranked_offers
    assert r1.price_norm == 1.0
    assert r1.bayesian_rating == 4.48
    assert r1.value_score == 95.32

    assert r2.price_norm == 0.8
    assert r2.bayesian_rating == 4.8471
    assert r2.value_score == 87.62

    assert r3.price_norm == 0.6
    assert r3.bayesian_rating == 4.7111
    assert r3.value_score == 75.4


def test_bayesian_one_review_five_star_trap() -> None:
    """T1.2 — 4.8-star / 600-review offer strictly outranks 5.0-star / 1-review trap."""
    offers = [
        _make_offer("trap-1rev", price="1500.00", rating=5.0, review_count=1),
        _make_offer("proven-600rev", price="1500.00", rating=4.8, review_count=600),
        _make_offer("baseline", price="2200.00", rating=4.1, review_count=60),
    ]
    intent = SearchIntent(query="Anker Earbuds", country=CountryCode.EG)

    result = rank_top_offers(offers, intent)
    by_id = {item.offer.offer_id: item for item in result.ranked_offers}

    assert [item.offer.offer_id for item in result.ranked_offers[:2]] == [
        "proven-600rev",
        "trap-1rev",
    ]
    assert by_id["trap-1rev"].bayesian_rating == pytest.approx(4.0385, abs=1e-4)
    assert by_id["proven-600rev"].bayesian_rating == pytest.approx(4.7680, abs=1e-4)
    assert by_id["proven-600rev"].value_score > by_id["trap-1rev"].value_score

    slightly_cheaper_trap = [
        _make_offer("trap-1rev", price="1490.00", rating=5.0, review_count=1),
        _make_offer("proven-600rev", price="1500.00", rating=4.8, review_count=600),
        _make_offer("baseline", price="2200.00", rating=4.1, review_count=60),
    ]
    result_cheaper = rank_top_offers(slightly_cheaper_trap, intent)
    assert result_cheaper.ranked_offers[0].offer.offer_id == "proven-600rev"


def test_unrated_and_zero_review_prior() -> None:
    """T1.3 — Unrated/zero-review offers stay eligible with conservative prior 3.4 (< 4.0)."""
    offers = [
        _make_offer("unrated-none", price="1500.00", rating=None, review_count=0),
        _make_offer("zero-reviews", price="1500.00", rating=5.0, review_count=0),
        _make_offer("reviewed-38", price="1500.00", rating=3.8, review_count=50),
    ]
    intent = SearchIntent(query="Anker Earbuds", country=CountryCode.EG)

    result = rank_top_offers(offers, intent)
    assert len(result.ranked_offers) == 3
    assert result.ranked_offers[0].offer.offer_id == "reviewed-38"
    assert result.ranked_offers[0].bayesian_rating == 3.8667

    for item in result.ranked_offers[1:]:
        assert item.bayesian_rating == 3.4
        assert item.bayesian_rating < ScoringConfig().bayesian_prior_mean
        assert "unrated_fallback" in item.match_reasons


def test_hard_filters_and_min_rating_excludes_unrated() -> None:
    """T1.4 — Hard filters drop ineligible/unrated offers prior to Stage 1/2 counts."""
    zero_price_defensive = ProductOffer.model_construct(
        offer_id="zero-price",
        title="Anker Soundcore Liberty 4 NC",
        price=Decimal("0.00"),
        currency=CurrencyCode.EGP,
        store=StoreId.NOON,
        country=CountryCode.EG,
        url="https://www.noon.com/egypt-en/zero-price",
        rating=4.9,
        review_count=200,
        in_stock=True,
    )
    offers = [
        _make_offer("oos", in_stock=False, store=StoreId.NOON, price="1200.00"),
        zero_price_defensive,
        _make_offer(
            "wrong-country",
            country=CountryCode.SA,
            store=StoreId.NOON,
            price="1200.00",
        ),
        _make_offer("wrong-store", store=StoreId.AMAZON, price="1200.00"),
        _make_offer("over-budget", store=StoreId.NOON, price="2500.00"),
        _make_offer(
            "low-rating", store=StoreId.NOON, price="1200.00", rating=3.9, review_count=100
        ),
        _make_offer("unrated", store=StoreId.NOON, price="1200.00", rating=None, review_count=0),
        _make_offer("zero-rev", store=StoreId.NOON, price="1200.00", rating=5.0, review_count=0),
        _make_offer(
            "valid-winner", store=StoreId.NOON, price="1800.00", rating=4.5, review_count=80
        ),
    ]
    intent = SearchIntent(
        query="Anker Soundcore",
        country=CountryCode.EG,
        store=StoreFilter.NOON,
        max_budget=Decimal("2000.00"),
        min_rating=4.0,
    )

    result = rank_top_offers(offers, intent)
    assert result.total_candidates == len(offers)
    assert result.filtered_accessories_count == 0
    assert result.filtered_outliers_count == 0
    assert result.degraded_fewer_than_k is True
    assert [item.offer.offer_id for item in result.ranked_offers] == ["valid-winner"]


def test_store_both_and_bilingual_exclude_keywords() -> None:
    """T1.5 — StoreFilter.BOTH retains Noon+Amazon while bilingual exclude_keywords filters."""
    offers = [
        _make_offer(
            "keep-noon",
            title="Anker Soundcore Liberty 4 NC",
            store=StoreId.NOON,
            price="1500.00",
        ),
        _make_offer(
            "keep-amazon",
            title="سماعة أنكر أصلية بلوتوث",
            store=StoreId.AMAZON,
            price="1600.00",
        ),
        _make_offer(
            "drop-en",
            title="Anker Soundcore Liberty 4 (REFURBISHED)",
            store=StoreId.AMAZON,
            price="1100.00",
        ),
        _make_offer(
            "drop-ar-plain",
            title="سماعة أنكر مجدد",
            store=StoreId.NOON,
            price="1100.00",
        ),
        _make_offer(
            "drop-ar-diacritics-fem",
            title="سماعة أنكر مُجَدَّدَة",
            store=StoreId.NOON,
            price="1100.00",
        ),
        _make_offer(
            "drop-ar-al",
            title="سماعة أنكر المجددة",
            store=StoreId.AMAZON,
            price="1100.00",
        ),
    ]
    intent = SearchIntent(
        query="Anker Soundcore",
        country=CountryCode.EG,
        store=StoreFilter.BOTH,
        exclude_keywords=("refurbished", "مجدد"),
    )

    result = rank_top_offers(offers, intent)
    assert result.filtered_accessories_count == 0
    assert {item.offer.offer_id for item in result.ranked_offers} == {
        "keep-noon",
        "keep-amazon",
    }


def test_stage1_bilingual_accessory_rejection() -> None:
    """T1.6 — Stage 1 rejects all EN/AR accessory terms without false positives on primary items."""
    en_accessories = [
        ("acc-en-case", "iPhone 15 Silicone Case"),
        ("acc-en-cover", "iPhone 15 Leather Cover"),
        ("acc-en-protector", "iPhone 15 Tempered Glass Protector"),
        ("acc-en-cable", "iPhone 15 Braided USB-C Cable"),
        ("acc-en-cord", "iPhone 15 Charging Cord"),
        ("acc-en-charger", "Apple 20W Fast Charger"),
        ("acc-en-adapter", "Lightning to 3.5mm Adapter"),
        ("acc-en-strap", "Silicone Lanyard Strap"),
        ("acc-en-holder", "Magnetic Car Phone Holder"),
        ("acc-en-mount", "Dashboard Phone Mount"),
        ("acc-en-skin", "Matte Carbon Back Skin"),
        ("acc-en-sleeve", "Neoprene Protective Sleeve"),
    ]
    en_primaries = [
        ("prim-en-1", "iPhone 15 128GB Black"),
        ("prim-en-2", "iPhone 15 Showcase Edition 256GB"),
        ("prim-en-3", "iPhone 15 Record Player Bundle"),
    ]
    en_offers = [
        _make_offer(oid, title=title, price="35000.00" if oid.startswith("prim") else "400.00")
        for oid, title in en_accessories + en_primaries
    ]
    en_result = rank_top_offers(en_offers, SearchIntent(query="iPhone 15", country=CountryCode.EG))
    assert en_result.filtered_accessories_count == len(en_accessories)
    assert en_result.filtered_outliers_count == 0
    assert {item.offer.offer_id for item in en_result.ranked_offers} == {
        "prim-en-1",
        "prim-en-2",
        "prim-en-3",
    }

    ar_accessories = [
        ("acc-ar-1", "جراب سيليكون سماعة أنكر"),
        ("acc-ar-2", "كفر حماية أنكر"),
        ("acc-ar-3", "حافظة سماعة بلوتوث أنكر"),
        ("acc-ar-4", "شاحن سريع أنكر 20 وات"),
        ("acc-ar-5", "اسكرينة حماية زجاج"),
        ("acc-ar-6", "حماية شاشة ضد الكسر"),
        ("acc-ar-7", "وصلة شحن تايب سي"),
        ("acc-ar-8", "كابل أنكر الأصلي"),
        ("acc-ar-9", "سلك شحن أنكر"),
        ("acc-ar-10", "حامل هاتف مكتبي"),
        ("acc-ar-11", "سوار تثبيت رياضي"),
        ("acc-ar-12", "الإسكرينة الأصلية وحماية الشاشة"),
    ]
    ar_primaries = [
        ("prim-ar-1", "سماعة بلوتوث لاسلكية أنكر ليبرتي 4"),
        ("prim-ar-2", "سماعة أنكر ساوندكور برو"),
        ("prim-ar-3", "سماعة بلوتوث أنكر أصلية"),
    ]
    ar_offers = [
        _make_offer(oid, title=title, price="3000.00" if oid.startswith("prim") else "200.00")
        for oid, title in ar_accessories + ar_primaries
    ]
    ar_result = rank_top_offers(
        ar_offers,
        SearchIntent(query="سماعة بلوتوث أنكر", country=CountryCode.EG, language="ar"),
    )
    assert ar_result.filtered_accessories_count == len(ar_accessories)
    assert ar_result.filtered_outliers_count == 0
    assert {item.offer.offer_id for item in ar_result.ranked_offers} == {
        "prim-ar-1",
        "prim-ar-2",
        "prim-ar-3",
    }


def test_stage1_positive_accessory_search_and_opt_in() -> None:
    """T1.7 — Positive accessory search retains matching term; include_accessories skips Stage 1."""
    en_offers = [
        _make_offer("case-1", title="Spigen iPhone 15 Case", price="700.00"),
        _make_offer("case-2", title="Apple iPhone 15 Clear Cases Pack", price="850.00"),
        _make_offer("charger-1", title="Anker 20W USB-C Charger", price="650.00"),
    ]
    en_case_result = rank_top_offers(
        en_offers,
        SearchIntent(query="iPhone 15 case", country=CountryCode.EG, language="en"),
    )
    assert en_case_result.filtered_accessories_count == 1
    assert {item.offer.offer_id for item in en_case_result.ranked_offers} == {"case-1", "case-2"}

    ar_offers = [
        _make_offer("ar-case-1", title="جراب سيليكون آيفون 15", price="350.00"),
        _make_offer("ar-case-2", title="الجراب الشفاف آيفون 15", price="400.00"),
        _make_offer("ar-charger", title="شاحن سريع آيفون 15", price="650.00"),
    ]
    ar_case_result = rank_top_offers(
        ar_offers,
        SearchIntent(query="جراب آيفون 15", country=CountryCode.EG, language="ar"),
    )
    assert ar_case_result.filtered_accessories_count == 1
    assert {item.offer.offer_id for item in ar_case_result.ranked_offers} == {
        "ar-case-1",
        "ar-case-2",
    }

    opt_in_result = rank_top_offers(
        en_offers,
        SearchIntent(
            query="iPhone 15",
            country=CountryCode.EG,
            include_accessories=True,
            language="en",
        ),
    )
    assert opt_in_result.filtered_accessories_count == 0
    assert len(opt_in_result.ranked_offers) == 3


def test_stage2_median_price_floor_ceiling_and_budget() -> None:
    """T1.8 — Stage 2 rejects <0.15*median & >3.0*median unless max_budget accommodates upper."""
    offers = [
        _make_offer("floor-outlier", price="149.99"),
        _make_offer("floor-boundary", price="150.00"),
        _make_offer("mid-a", price="950.00"),
        _make_offer("mid-median", price="1000.00"),
        _make_offer("mid-b", price="1100.00"),
        _make_offer("ceiling-boundary", price="3000.00"),
        _make_offer("upper-scalper", price="3500.00"),
    ]
    no_budget_result = rank_top_offers(
        offers,
        SearchIntent(query="Wireless Mouse", country=CountryCode.EG),
        config=ScoringConfig(top_k=3),
    )
    # Sorted prices: [149.99, 150.00, 950.00, 1000.00, 1100.00, 3000.00, 3500.00] -> median 1000.00
    assert no_budget_result.filtered_outliers_count == 2
    returned_ids = {item.offer.offer_id for item in no_budget_result.ranked_offers}
    assert "floor-outlier" not in returned_ids
    assert "upper-scalper" not in returned_ids
    assert "floor-boundary" in returned_ids

    # Narrower pool verifying 3500.00 is preserved when max_budget=4000.00 while 140.00 is dropped
    budget_pool = [
        _make_offer("cheap-outlier", price="140.00", rating=4.9, review_count=500),
        _make_offer("normal-low", price="900.00", rating=4.1, review_count=30),
        _make_offer("normal-mid", price="1000.00", rating=4.2, review_count=30),
        _make_offer("normal-high", price="1100.00", rating=4.3, review_count=30),
        _make_offer("high-tier", price="3500.00", rating=5.0, review_count=1000),
    ]
    budget_result = rank_top_offers(
        budget_pool,
        SearchIntent(
            query="Wireless Mouse",
            country=CountryCode.EG,
            max_budget=Decimal("4000.00"),
        ),
        config=ScoringConfig(price_weight=0.0, rating_weight=1.0),
    )
    assert budget_result.filtered_outliers_count == 1
    assert budget_result.ranked_offers[0].offer.offer_id == "high-tier"
    assert all(item.offer.offer_id != "cheap-outlier" for item in budget_result.ranked_offers)


def test_configurable_scoring_weights_override() -> None:
    """T1.9 — Custom ScoringConfig shifts winner toward rating and caps output to top_k=2."""
    offers = [
        _make_offer("budget-pick", price="1000.00", rating=2.8, review_count=30),
        _make_offer("quality-pick", price="1800.00", rating=4.95, review_count=200),
        _make_offer("unrated-pick", price="1200.00", rating=None, review_count=0),
    ]
    intent = SearchIntent(query="Bluetooth Speaker", country=CountryCode.EG)

    default_res = rank_top_offers(offers, intent)
    assert default_res.ranked_offers[0].offer.offer_id == "budget-pick"
    assert len(default_res.ranked_offers) == 3

    custom_cfg = ScoringConfig(
        price_weight=0.20,
        rating_weight=0.80,
        bayesian_prior_count=10,
        unrated_prior_rating=3.0,
        top_k=2,
    )
    custom_res = rank_top_offers(offers, intent, config=custom_cfg)
    assert len(custom_res.ranked_offers) == 2
    assert custom_res.degraded_fewer_than_k is False
    assert custom_res.ranked_offers[0].offer.offer_id == "quality-pick"

    unrated_only = rank_top_offers([offers[2]], intent, config=custom_cfg)
    assert unrated_only.ranked_offers[0].bayesian_rating == 3.0


def test_match_reasons_and_offer_immutability() -> None:
    """T1.10 — Deterministic grounded match_reasons and untouched ProductOffer instances."""
    offers = [
        _make_offer("best-rated", price="1150.00", rating=4.9, review_count=300),
        _make_offer("cheapest", price="1000.00", rating=4.3, review_count=15),
        _make_offer("middle-runner", price="1400.00", rating=4.3, review_count=10),
        _make_offer("unrated-item", price="1250.00", rating=None, review_count=0),
    ]
    snapshots = [offer.model_copy(deep=True) for offer in offers]
    intent = SearchIntent(
        query="Anker Soundcore",
        country=CountryCode.EG,
        max_budget=Decimal("2000.00"),
    )

    result = rank_top_offers(offers, intent)
    by_id = {item.offer.offer_id: item for item in result.ranked_offers}

    assert "best_overall_value" in result.ranked_offers[0].match_reasons
    assert "lowest_price" in by_id["cheapest"].match_reasons
    assert "top_bayesian_rating" in by_id["best-rated"].match_reasons
    assert "high_review_confidence" in by_id["best-rated"].match_reasons
    assert "high_review_confidence" not in by_id["cheapest"].match_reasons
    assert "unrated_fallback" in by_id["unrated-item"].match_reasons
    for item in result.ranked_offers:
        assert len(item.match_reasons) >= 1
        assert "within_budget" in item.match_reasons

    # Verify runner-up without price/rating/confidence/budget tags receives strong_value_runner_up
    runner_pool = [
        _make_offer("r1", price="1000.00", rating=4.9, review_count=100),
        _make_offer("r2", price="1200.00", rating=4.5, review_count=5),
        _make_offer("r3", price="1300.00", rating=4.2, review_count=5),
    ]
    runner_res = rank_top_offers(
        runner_pool,
        SearchIntent(query="Anker Soundcore", country=CountryCode.EG),
    )
    assert runner_res.ranked_offers[1].match_reasons == ("strong_value_runner_up",)
    assert runner_res.ranked_offers[2].match_reasons == ("strong_value_runner_up",)

    # Verify original ProductOffer instances are completely unmodified
    assert offers == snapshots
    original_by_id = {offer.offer_id: offer for offer in snapshots}
    for ranked in result.ranked_offers:
        assert ranked.offer == original_by_id[ranked.offer.offer_id]


def test_zero_vendor_imports_hexagonal_boundary() -> None:
    """T1.11 — domain/ranking.py uses stdlib + domain/config only with zero vendor SDK imports."""
    forbidden_prefixes = (
        "commerce_ai.adapters",
        "httpx",
        "redis",
        "serper",
        "langfuse",
        "boto3",
        "openai",
        "litellm",
        "langgraph",
        "fastapi",
        "sqlalchemy",
    )
    source = RANKING_MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(RANKING_MODULE_PATH))

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    for module_name in imported_modules:
        top_pkg = module_name.split(".")[0]
        assert not any(
            module_name == bad or module_name.startswith(f"{bad}.") for bad in forbidden_prefixes
        ), f"Forbidden import in ranking.py: {module_name}"
        is_allowed_internal = module_name.startswith(("commerce_ai.domain", "commerce_ai.config"))
        is_stdlib = top_pkg in sys.stdlib_module_names
        assert is_allowed_internal or is_stdlib, f"Unexpected third-party import: {module_name}"


def test_empty_and_all_filtered_graceful_degradation() -> None:
    """T3.1 — Empty input and total filter elimination degrade gracefully without exceptions."""
    intent = SearchIntent(query="iPhone 15", country=CountryCode.EG)

    empty_res = rank_top_offers([], intent)
    assert empty_res.ranked_offers == []
    assert empty_res.total_candidates == 0
    assert empty_res.filtered_accessories_count == 0
    assert empty_res.filtered_outliers_count == 0
    assert empty_res.degraded_fewer_than_k is True

    eliminated_offers = [
        _make_offer("acc-1", title="iPhone 15 Silicone Case", price="300.00"),
        _make_offer("oos-1", title="iPhone 15", in_stock=False, price="35000.00"),
    ]
    eliminated_res = rank_top_offers(eliminated_offers, intent)
    assert eliminated_res.ranked_offers == []
    assert eliminated_res.total_candidates == 2
    assert eliminated_res.filtered_accessories_count == 1
    assert eliminated_res.filtered_outliers_count == 0
    assert eliminated_res.degraded_fewer_than_k is True


def test_partial_matches_degraded_flag_no_padding() -> None:
    """T3.2 — 1 or 2 qualifying offers set degraded_fewer_than_k=True with zero padding."""
    intent = SearchIntent(query="Anker Earbuds", country=CountryCode.SA)

    one_res = rank_top_offers(
        [_make_offer("sa-1", country=CountryCode.SA, price="450.00")],
        intent,
    )
    assert len(one_res.ranked_offers) == 1
    assert one_res.ranked_offers[0].rank == 1
    assert one_res.degraded_fewer_than_k is True

    two_res = rank_top_offers(
        [
            _make_offer("sa-1", country=CountryCode.SA, price="450.00"),
            _make_offer("sa-2", country=CountryCode.SA, price="500.00"),
        ],
        intent,
    )
    assert len(two_res.ranked_offers) == 2
    assert [item.rank for item in two_res.ranked_offers] == [1, 2]
    assert two_res.degraded_fewer_than_k is True


def test_single_candidate_and_equal_price_norm() -> None:
    """T3.3 — Single candidate and equal-price pools produce P_norm == 1.0 cleanly."""
    intent = SearchIntent(query="Anker Earbuds", country=CountryCode.AE)

    single_res = rank_top_offers(
        [_make_offer("ae-single", country=CountryCode.AE, price="299.00", rating=4.7)],
        intent,
    )
    assert len(single_res.ranked_offers) == 1
    assert single_res.ranked_offers[0].price_norm == 1.0
    assert 0.0 <= single_res.ranked_offers[0].value_score <= 100.0

    equal_pool = [
        _make_offer("ae-1", country=CountryCode.AE, price="299.00", rating=4.2, review_count=40),
        _make_offer("ae-2", country=CountryCode.AE, price="299.00", rating=4.8, review_count=150),
        _make_offer("ae-3", country=CountryCode.AE, price="299.00", rating=4.5, review_count=80),
    ]
    equal_res = rank_top_offers(equal_pool, intent)
    assert equal_res.degraded_fewer_than_k is False
    assert [item.offer.offer_id for item in equal_res.ranked_offers] == ["ae-2", "ae-3", "ae-1"]
    for item in equal_res.ranked_offers:
        assert item.price_norm == 1.0
        assert 0.0 <= item.value_score <= 100.0


def test_stage2_inactive_below_min_candidates() -> None:
    """T3.4 — Stage 2 outlier guard stays inactive when fewer than 3 candidates remain."""
    intent = SearchIntent(query="Smart Watch", country=CountryCode.EG)

    res_pair = rank_top_offers(
        [
            _make_offer("low", price="100.00"),
            _make_offer("high", price="1000.00"),
        ],
        intent,
    )
    assert res_pair.filtered_outliers_count == 0
    assert len(res_pair.ranked_offers) == 2

    # Even with >10x spread, len == 2 (< min_candidates_for_outlier_guard=3) must not filter
    res_wide_pair = rank_top_offers(
        [
            _make_offer("low", price="100.00"),
            _make_offer("high", price="2000.00"),
        ],
        intent,
    )
    assert res_wide_pair.filtered_outliers_count == 0
    assert len(res_wide_pair.ranked_offers) == 2


def test_stage1_runs_before_stage2_median() -> None:
    """T3.5 — Stage 1 removes cheap accessories before Stage 2 computes the median price."""
    offers = [
        _make_offer("phone-1", title="Samsung Galaxy S24", price="20000.00"),
        _make_offer("phone-2", title="Samsung Galaxy S24 256GB", price="21000.00"),
        _make_offer("phone-3", title="Samsung Galaxy S24 Dual SIM", price="19500.00"),
        _make_offer("acc-1", title="Galaxy S24 Silicone Case", price="150.00"),
        _make_offer("acc-2", title="Galaxy S24 Screen Protector", price="120.00"),
        _make_offer("acc-3", title="USB-C Charger 25W", price="180.00"),
        _make_offer("acc-4", title="جراب سامسونج S24", price="140.00"),
    ]
    intent = SearchIntent(query="Samsung Galaxy S24", country=CountryCode.EG)

    result = rank_top_offers(offers, intent)
    assert result.filtered_accessories_count == 4
    assert result.filtered_outliers_count == 0
    assert {item.offer.offer_id for item in result.ranked_offers} == {
        "phone-1",
        "phone-2",
        "phone-3",
    }


def test_tie_breaking_review_count_price_offer_id() -> None:
    """T3.6 — Exact value_score ties break by -review_count, then +price, then +offer_id."""
    intent = SearchIntent(query="Anker Earbuds", country=CountryCode.EG)

    # 1. rating == bayesian_prior_mean (4.0) yields identical bayesian_rating (4.0) across counts
    rev_tie_offers = [
        _make_offer("rev-low", price="1500.00", rating=4.0, review_count=50),
        _make_offer("rev-high", price="1500.00", rating=4.0, review_count=300),
    ]
    rev_res = rank_top_offers(rev_tie_offers, intent)
    assert rev_res.ranked_offers[0].value_score == rev_res.ranked_offers[1].value_score
    assert [item.offer.offer_id for item in rev_res.ranked_offers] == ["rev-high", "rev-low"]

    # 2. Equal value_score (price_weight=0.0) and equal review_count -> lower price wins
    price_tie_cfg = ScoringConfig(price_weight=0.0, rating_weight=1.0)
    price_tie_offers = [
        _make_offer("pricier", price="1600.00", rating=4.5, review_count=100),
        _make_offer("cheaper", price="1200.00", rating=4.5, review_count=100),
    ]
    price_res = rank_top_offers(price_tie_offers, intent, config=price_tie_cfg)
    assert price_res.ranked_offers[0].value_score == price_res.ranked_offers[1].value_score
    assert [item.offer.offer_id for item in price_res.ranked_offers] == ["cheaper", "pricier"]

    # 3. Equal value_score, review_count, and price -> lexicographical offer_id wins
    id_tie_offers = [
        _make_offer("offer-c", price="1500.00", rating=4.6, review_count=100),
        _make_offer("offer-a", price="1500.00", rating=4.6, review_count=100),
        _make_offer("offer-b", price="1500.00", rating=4.6, review_count=100),
    ]
    id_res = rank_top_offers(id_tie_offers, intent)
    assert [item.offer.offer_id for item in id_res.ranked_offers] == [
        "offer-a",
        "offer-b",
        "offer-c",
    ]


def test_offline_determinism_and_performance_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """T3.7 — 100-offer ranking executes offline with zero sockets in < 5 ms per call."""

    def _forbid_socket(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Network sockets are forbidden in deterministic unit tests")

    monkeypatch.setattr(socket, "socket", _forbid_socket)
    for key in ("SERPER_API_KEY", "REDIS_URL", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    offers: list[ProductOffer] = []
    for idx in range(70):
        offers.append(
            _make_offer(
                f"prod-{idx:03d}",
                title=f"Anker Soundcore Earbuds Edition {idx}",
                price=Decimal("1800.00") + Decimal(idx * 15),
                store=StoreId.AMAZON if idx % 2 == 0 else StoreId.NOON,
                rating=None if idx % 11 == 0 else round(3.8 + (idx % 12) * 0.1, 2),
                review_count=0 if idx % 11 == 0 else 10 + idx * 5,
            )
        )
    for idx in range(20):
        offers.append(
            _make_offer(
                f"acc-{idx:03d}",
                title=f"جراب حماية أنكر {idx}" if idx % 2 == 0 else f"Silicone Case {idx}",
                price=Decimal("150.00"),
            )
        )
    for idx in range(10):
        offers.append(
            _make_offer(
                f"out-{idx:03d}",
                title=f"Anker Soundcore Earbuds Scalper {idx}",
                price=Decimal("12000.00"),
                rating=5.0,
                review_count=1,
            )
        )

    assert len(offers) == 100
    intent = SearchIntent(query="Anker Soundcore Earbuds", country=CountryCode.EG)

    baseline = rank_top_offers(offers, intent)
    start = time.perf_counter()
    for _ in range(20):
        repeated = rank_top_offers(offers, intent)
        assert repeated == baseline
    avg_seconds = (time.perf_counter() - start) / 20.0

    assert avg_seconds < 0.005, (
        f"Expected < 5 ms per 100-offer ranking call, got {avg_seconds:.6f}s"
    )
