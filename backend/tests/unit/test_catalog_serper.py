"""Offline MockTransport unit & error tests for SerperShoppingProvider and catalog factory."""

import json
import logging
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from commerce_ai.adapters.cache.memory import InMemoryTTLCache
from commerce_ai.adapters.catalog import serper_provider as serper_module
from commerce_ai.adapters.catalog.cached_provider import CachedCatalogProvider
from commerce_ai.adapters.catalog.factory import create_catalog_provider
from commerce_ai.adapters.catalog.seed_provider import SeedCatalogProvider
from commerce_ai.adapters.catalog.serper_provider import (
    SERPER_SHOPPING_URL,
    SerperShoppingProvider,
)
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.errors import CatalogProviderError
from commerce_ai.domain.models import (
    CatalogSourceMode,
    CountryCode,
    CurrencyCode,
    SearchIntent,
    StoreFilter,
    StoreId,
)
from commerce_ai.domain.ports import CatalogProvider


async def test_serper_sends_single_configured_shopping_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T1.7 — SerperShoppingProvider issues strictly 1 POST /shopping call with P5 settings."""
    monkeypatch.delenv("SERPER_TIMEOUT_SECONDS", raising=False)
    cases = [
        (CountryCode.EG, "ar", StoreFilter.BOTH, "سماعة بلوتوث", "eg", "سماعة بلوتوث"),
        (CountryCode.SA, "en", StoreFilter.NOON, "Anker earbuds", "sa", "Anker earbuds noon"),
        (CountryCode.AE, "en", StoreFilter.AMAZON, "iPhone 15", "ae", "iPhone 15 amazon"),
    ]
    default_timeout = AppSettings(_env_file=None).serper_timeout_seconds
    assert default_timeout == 2.0

    for country, language, store_filter, query, expected_gl, expected_q in cases:
        captured: list[httpx.Request] = []

        def handler(
            request: httpx.Request,
            *,
            sink: list[httpx.Request] = captured,
        ) -> httpx.Response:
            sink.append(request)
            return httpx.Response(200, json={"shopping": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SerperShoppingProvider(
                api_key=SecretStr("test-serper-key"),
                timeout_seconds=default_timeout,
                client=client,
            )
            assert isinstance(provider, CatalogProvider)
            intent = SearchIntent(
                query=query,
                country=country,
                store=store_filter,
                language=language,  # type: ignore[arg-type]
            )
            result = await provider.search_offers(intent)

        assert result.source_mode == CatalogSourceMode.LIVE
        assert result.cache_hit is False
        assert len(captured) == 1

        req = captured[0]
        assert req.method == "POST"
        assert str(req.url) == SERPER_SHOPPING_URL
        assert req.headers["x-api-key"] == "test-serper-key"
        assert req.extensions["timeout"]["read"] == 2.0
        assert req.extensions["timeout"]["connect"] == 2.0

        body = json.loads(req.content.decode("utf-8"))
        assert body == {
            "q": expected_q,
            "gl": expected_gl,
            "hl": language,
            "num": 40,
        }


async def test_serper_parses_official_and_attributed_google_shopping_offers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T1.8 — Serper parses official regional URLs & attributed Google Shopping links."""
    validation_calls: list[tuple[str, CountryCode, StoreId, str | None]] = []
    real_validator = serper_module.validate_regional_offer_url

    def spy_validator(
        url: str,
        *,
        country: CountryCode,
        store: StoreId,
        merchant_attribution: str | None = None,
    ) -> str:
        validation_calls.append((url, country, store, merchant_attribution))
        return real_validator(
            url,
            country=country,
            store=store,
            merchant_attribution=merchant_attribution,
        )

    monkeypatch.setattr(serper_module, "validate_regional_offer_url", spy_validator)

    payload = {
        "shopping": [
            {
                "title": "Anker Soundcore Liberty 4 NC",
                "source": "Amazon.eg",
                "link": "https://www.amazon.eg/dp/B0C1234567",
                "price": "EGP 3,499.00",
                "rating": 4.7,
                "ratingCount": 420,
                "imageUrl": "https://m.media-amazon.com/images/I/example.jpg",
                "productId": "eg-amz-1",
            },
            {
                "title": "سماعة بلوتوث أنكر ساوندكور",
                "source": "noon.com",
                "link": "https://www.noon.com/egypt-ar/anker-earbuds/N123/p/",
                "price": "٣٬٢٩٩٫٥٠ ج.م",
                "rating": 4.6,
                "ratingCount": "1,150",
                "imageUrl": "https://f.nooncdn.com/p/example.jpg",
                "productId": "eg-noon-1",
            },
            {
                "title": "Anker Soundcore R50i",
                "source": "Amazon.eg",
                "link": "https://www.google.com/shopping/product/123456",
                "price": "1,199 EGP",
                "rating": 4.5,
                "ratingCount": 210,
            },
            {
                "title": "Anker Soundcore Space A40",
                "source": "Noon Egypt",
                "link": "https://www.google.com.eg/shopping/product/654321",
                "price": "3650.256",
                "rating": None,
                "productId": "dup-1",
            },
            {
                "title": "Anker Soundcore Duplicate ID",
                "source": "Amazon.eg",
                "link": "https://www.amazon.eg/dp/B0DUPID001",
                "price": 1999,
                "rating": 5.5,
                "productId": "dup-1",
            },
            {
                "title": "Anker Soundcore Decimal Price",
                "source": "Amazon.eg",
                "link": "https://www.amazon.eg/dp/B0DEC00001",
                "price": 199.5,
                "rating": -1.0,
            },
        ]
    }

    transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        provider = SerperShoppingProvider(api_key=SecretStr("key-123"), client=client)
        result = await provider.search_offers(
            SearchIntent(query="Anker earbuds", country=CountryCode.EG)
        )

    assert result.source_mode == CatalogSourceMode.LIVE
    assert result.cache_hit is False
    assert len(result.offers) == 6
    assert len(validation_calls) == 6

    assert result.offers[0].store == StoreId.AMAZON
    assert result.offers[0].currency == CurrencyCode.EGP
    assert result.offers[0].price == Decimal("3499.00")
    assert result.offers[0].rating == 4.7
    assert result.offers[0].review_count == 420

    assert result.offers[1].store == StoreId.NOON
    assert result.offers[1].price == Decimal("3299.50")
    assert result.offers[1].review_count == 1150

    assert result.offers[2].store == StoreId.AMAZON
    assert str(result.offers[2].url) == "https://www.google.com/shopping/product/123456"
    assert result.offers[2].price == Decimal("1199.00")

    assert result.offers[3].store == StoreId.NOON
    assert result.offers[3].offer_id == "serper-noon-dup-1"
    assert result.offers[3].price == Decimal("3650.26")
    assert result.offers[3].rating is None
    assert result.offers[3].review_count == 0

    assert result.offers[4].offer_id == "serper-amazon-dup-1"
    assert result.offers[4].price == Decimal("1999.00")
    assert result.offers[4].rating is None

    assert result.offers[5].price == Decimal("199.50")
    assert result.offers[5].rating is None

    # Duplicate same-store productId gets -2 suffix and Arabic SAR text parses cleanly.
    sa_payload = {
        "shopping": [
            {
                "title": "Anker SA First",
                "source": "Amazon.sa",
                "link": "https://www.amazon.sa/dp/B0SAR1",
                "price": "199 ر.س",
                "productId": "same-1",
            },
            {
                "title": "Anker SA Second",
                "source": "Amazon.sa",
                "link": "https://www.amazon.sa/dp/B0SAR2",
                "price": "SAR 250",
                "productId": "same-1",
            },
        ]
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _req: httpx.Response(200, json=sa_payload))
    ) as client:
        sa_provider = SerperShoppingProvider(api_key=SecretStr("key-123"), client=client)
        sa_res = await sa_provider.search_offers(
            SearchIntent(query="Anker", country=CountryCode.SA)
        )
    assert [o.offer_id for o in sa_res.offers] == [
        "serper-amazon-same-1",
        "serper-amazon-same-1-2",
    ]
    assert sa_res.offers[0].price == Decimal("199.00")


async def test_serper_filters_out_cross_country_and_third_party_offers() -> None:
    """T1.9 — Serper rejects cross-country, non-HTTPS, unattributed, and third-party items."""
    payload = {
        "shopping": [
            {
                "title": "Valid Amazon Egypt Offer",
                "source": "Amazon.eg",
                "link": "https://www.amazon.eg/dp/B0VALID1",
                "price": "EGP 2,500.00",
                "rating": 4.7,
                "ratingCount": 150,
            },
            {
                "title": "Valid Noon Egypt via Google Shopping",
                "source": "Noon Egypt",
                "link": "https://www.google.com.eg/shopping/product/99901",
                "price": "EGP 2,400.00",
            },
            {
                "title": "US Amazon Cross-Country Offer",
                "source": "Amazon.com",
                "link": "https://www.amazon.com/dp/B0US123",
                "price": "EGP 2,100.00",
            },
            {
                "title": "Saudi Amazon Wrong Country Offer",
                "source": "Amazon.sa",
                "link": "https://www.amazon.sa/dp/B0SA123",
                "price": "EGP 2,100.00",
            },
            {
                "title": "Insecure HTTP Amazon Egypt Offer",
                "source": "Amazon.eg",
                "link": "http://www.amazon.eg/dp/B0HTTP",
                "price": "EGP 2,100.00",
            },
            {
                "title": "Unattributed Google Shopping Link",
                "source": "",
                "link": "https://www.google.com/shopping/product/11111",
                "price": "EGP 2,100.00",
            },
            {
                "title": "Third-Party B.TECH on Google Shopping",
                "source": "B.TECH",
                "link": "https://www.google.com/shopping/product/22222",
                "price": "EGP 2,100.00",
            },
            {
                "title": "Foreign Amazon.com on Google Shopping",
                "source": "Amazon.com",
                "link": "https://www.google.com/shopping/product/33333",
                "price": "EGP 2,100.00",
            },
            {
                "title": "Third-Party Jumia Direct URL",
                "source": "Jumia",
                "link": "https://www.jumia.com.eg/product/123",
                "price": "EGP 2,100.00",
            },
            {
                "title": "Foreign USD Symbol Price on Amazon Egypt Google Link",
                "source": "Amazon.eg",
                "link": "https://www.google.com/shopping/product/44444",
                "price": "$199.99",
            },
            {
                "title": "Foreign USD Code Price on Amazon Egypt Google Link",
                "source": "Amazon.eg",
                "link": "https://www.google.com/shopping/product/55555",
                "price": "USD 199.99",
            },
            {
                "title": "Ambiguous Price Range on Amazon Egypt",
                "source": "Amazon.eg",
                "link": "https://www.amazon.eg/dp/B0RANGE",
                "price": "EGP 100 - 200",
            },
        ]
    }

    transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        provider = SerperShoppingProvider(api_key=SecretStr("key-123"), client=client)
        both_res = await provider.search_offers(
            SearchIntent(query="earbuds", country=CountryCode.EG, store=StoreFilter.BOTH)
        )
        noon_only = await provider.search_offers(
            SearchIntent(query="earbuds", country=CountryCode.EG, store=StoreFilter.NOON)
        )
        amazon_only = await provider.search_offers(
            SearchIntent(query="earbuds", country=CountryCode.EG, store=StoreFilter.AMAZON)
        )

    assert [o.title for o in both_res.offers] == [
        "Valid Amazon Egypt Offer",
        "Valid Noon Egypt via Google Shopping",
    ]
    assert [o.title for o in noon_only.offers] == ["Valid Noon Egypt via Google Shopping"]
    assert [o.title for o in amazon_only.offers] == ["Valid Amazon Egypt Offer"]


async def test_serper_timeout_raises_retriable_error_without_seed_fallback() -> None:
    """T3.1 — Request timeout raises retriable CatalogProviderError with zero seed fallback."""

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out at 2.0s", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as client:
        provider = SerperShoppingProvider(
            api_key=SecretStr("key-123"),
            timeout_seconds=2.0,
            client=client,
        )
        with pytest.raises(CatalogProviderError) as exc_info:
            await provider.search_offers(SearchIntent(query="Anker", country=CountryCode.EG))

    assert exc_info.value.provider == "serper"
    assert exc_info.value.retriable is True
    assert "timed out" in exc_info.value.reason.lower()


async def test_serper_http_and_schema_errors_raise_typed_error() -> None:
    """T3.2 — Non-2xx statuses and malformed JSON/schemas raise accurate CatalogProviderError."""
    error_cases: list[tuple[httpx.Response, bool]] = [
        (httpx.Response(401, json={"message": "Unauthorized"}), False),
        (httpx.Response(403, json={"message": "Forbidden"}), False),
        (httpx.Response(400, json={"message": "Bad Request"}), False),
        (httpx.Response(404, json={"message": "Not Found"}), False),
        (httpx.Response(429, json={"message": "Rate limit"}), True),
        (httpx.Response(500, json={"message": "Internal error"}), True),
        (httpx.Response(503, json={"message": "Service unavailable"}), True),
        (httpx.Response(200, content=b"{invalid-json"), False),
        (httpx.Response(200, json=["not", "an", "object"]), False),
        (httpx.Response(200, json={"searchParameters": {}}), False),
        (httpx.Response(200, json={"shopping": {"not": "a-list"}}), False),
    ]

    for fake_response, expected_retriable in error_cases:
        transport = httpx.MockTransport(lambda _req, resp=fake_response: resp)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = SerperShoppingProvider(api_key=SecretStr("key-123"), client=client)
            with pytest.raises(CatalogProviderError) as exc_info:
                await provider.search_offers(SearchIntent(query="iPhone", country=CountryCode.SA))
        assert exc_info.value.provider == "serper"
        assert exc_info.value.retriable is expected_retriable


async def test_serper_never_logs_or_leaks_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T3.3 — SERPER_API_KEY never leaks in raised errors or logs."""
    secret = "serper-secret-test-999"

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            f"connection failed with X-API-KEY={secret}",
            request=request,
        )

    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(transport=httpx.MockTransport(failing_handler)) as client:
            provider = SerperShoppingProvider(api_key=SecretStr(secret), client=client)
            with pytest.raises(CatalogProviderError) as exc_info:
                await provider.search_offers(SearchIntent(query="laptop", country=CountryCode.AE))

    assert exc_info.value.retriable is True
    assert secret not in exc_info.value.reason
    assert secret not in str(exc_info.value)
    assert secret not in caplog.text

    def decoding_error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.DecodingError(
            f"failed to decode response body (X-API-KEY={secret})",
            request=request,
        )

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(decoding_error_handler)
        ) as client:
            provider = SerperShoppingProvider(api_key=SecretStr(secret), client=client)
            with pytest.raises(CatalogProviderError) as dec_exc:
                await provider.search_offers(SearchIntent(query="laptop", country=CountryCode.AE))

    assert dec_exc.value.provider == "serper"
    assert dec_exc.value.retriable is False
    assert secret not in dec_exc.value.reason
    assert secret not in caplog.text


async def test_serper_skips_malformed_items_and_handles_empty_results() -> None:
    """T3.4 — Invalid Serper entries are skipped cleanly and empty lists return empty LIVE."""
    mixed_payload = {
        "shopping": [
            "not-a-dict",
            {
                "title": "Missing URL Item",
                "source": "Amazon.ae",
                "price": "AED 199.00",
            },
            {
                "title": "Invalid N/A Price",
                "source": "Amazon.ae",
                "link": "https://www.amazon.ae/dp/B0NA",
                "price": "N/A",
            },
            {
                "title": "   ",
                "source": "Amazon.ae",
                "link": "https://www.amazon.ae/dp/B0BLANK",
                "price": "AED 199.00",
            },
            {
                "title": "Malformed IPv6 URL Item",
                "source": "Amazon.ae",
                "link": "https://[::1/bad",
                "price": "AED 199.00",
            },
            {
                "title": "Valid UAE Offer with Insecure Thumbnail Stripped",
                "source": "Amazon.ae",
                "link": "https://www.amazon.ae/dp/B0GOOD1",
                "price": "AED 499.00",
                "imageUrl": "http://insecure.example.com/img.jpg",
            },
            {
                "title": "Valid UAE Offer with Malformed IPv6 Thumbnail Stripped",
                "source": "Amazon.ae",
                "link": "https://www.amazon.ae/dp/B0GOOD2",
                "price": "AED 599.00",
                "imageUrl": "https://[::1/bad",
            },
        ]
    }

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _req: httpx.Response(200, json=mixed_payload))
    ) as client:
        provider = SerperShoppingProvider(api_key=SecretStr("key-123"), client=client)
        mixed_res = await provider.search_offers(
            SearchIntent(query="air fryer", country=CountryCode.AE)
        )

    assert mixed_res.source_mode == CatalogSourceMode.LIVE
    assert mixed_res.cache_hit is False
    assert len(mixed_res.offers) == 2
    assert mixed_res.offers[0].title == "Valid UAE Offer with Insecure Thumbnail Stripped"
    assert mixed_res.offers[0].image_url is None
    assert mixed_res.offers[1].title == "Valid UAE Offer with Malformed IPv6 Thumbnail Stripped"
    assert mixed_res.offers[1].image_url is None

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _req: httpx.Response(200, json={"shopping": []}))
    ) as client:
        provider = SerperShoppingProvider(api_key=SecretStr("key-123"), client=client)
        empty_res = await provider.search_offers(
            SearchIntent(query="air fryer", country=CountryCode.AE)
        )

    assert empty_res.offers == []
    assert empty_res.source_mode == CatalogSourceMode.LIVE
    assert empty_res.cache_hit is False


def test_catalog_factory_mode_resolution() -> None:
    """T1.10 — Catalog factory deterministically resolves Seed vs Serper based on catalog_mode."""
    seed_with_key = AppSettings(
        _env_file=None,
        catalog_mode="seed",
        serper_api_key=SecretStr("live-key"),
    )
    assert isinstance(create_catalog_provider(seed_with_key), SeedCatalogProvider)

    auto_without_key = AppSettings(_env_file=None, catalog_mode="auto", serper_api_key=None)
    assert isinstance(create_catalog_provider(auto_without_key), SeedCatalogProvider)

    auto_with_key = AppSettings(
        _env_file=None,
        catalog_mode="auto",
        serper_api_key=SecretStr("live-key"),
    )
    assert isinstance(create_catalog_provider(auto_with_key), SerperShoppingProvider)

    serper_with_key = AppSettings(
        _env_file=None,
        catalog_mode="serper",
        serper_api_key=SecretStr("live-key"),
    )
    assert isinstance(create_catalog_provider(serper_with_key), SerperShoppingProvider)

    wrapped = create_catalog_provider(auto_without_key, cache=InMemoryTTLCache())
    assert isinstance(wrapped, CachedCatalogProvider)


def test_catalog_factory_serper_mode_requires_api_key() -> None:
    """T3.10 — Explicit catalog_mode='serper' without key raises non-retriable error."""
    for bad_key in (None, SecretStr(""), SecretStr("   ")):
        settings = AppSettings(_env_file=None, catalog_mode="serper", serper_api_key=bad_key)
        with pytest.raises(CatalogProviderError) as exc_info:
            create_catalog_provider(settings)
        assert exc_info.value.provider == "serper"
        assert exc_info.value.retriable is False
