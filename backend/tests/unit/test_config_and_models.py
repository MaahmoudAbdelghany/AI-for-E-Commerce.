"""Offline deterministic unit tests for Feature 1.1 scaffold, config, and domain models."""

import ast
import importlib
import re
import tomllib
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from commerce_ai.config import (
    MARKET_REGISTRY,
    AppSettings,
    MarketConfig,
    ScoringConfig,
    redact_url_password,
    validate_regional_offer_url,
)
from commerce_ai.domain import (
    CacheStoreError,
    CatalogProviderError,
    CatalogSearchResult,
    CatalogSourceMode,
    ChatTurnResult,
    CountryCode,
    CurrencyCode,
    DomainError,
    LLMMessage,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    OfferValidationError,
    ProductOffer,
    RankedOffer,
    RankingResult,
    SearchIntent,
    SessionState,
    SessionStoreError,
    SessionTurn,
    StoreFilter,
    StoreId,
    TurnAction,
    TurnStatus,
    TurnTelemetry,
)
from commerce_ai.domain.models import _validate_positive_currency_decimal
from commerce_ai.domain.ports import LLMClient, SessionRepository

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


def _make_offer_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "offer_id": "offer-eg-1",
        "title": "Anker Soundcore Liberty 4 NC",
        "price": Decimal("3499.50"),
        "currency": CurrencyCode.EGP,
        "store": StoreId.AMAZON,
        "country": CountryCode.EG,
        "url": "https://www.amazon.eg/dp/B0C1234567",
        "rating": 4.7,
        "review_count": 420,
        "image_url": "https://m.media-amazon.com/images/I/example.jpg",
        "in_stock": True,
    }
    payload.update(overrides)
    return payload


def test_package_scaffold_and_pyproject_contract() -> None:
    """T1.1 — Phase 1 & Phase 2 package imports and pyproject.toml contracts are present."""
    for module_name in (
        "commerce_ai",
        "commerce_ai.config",
        "commerce_ai.domain",
        "commerce_ai.agent",
        "commerce_ai.adapters",
        "commerce_ai.adapters.catalog",
        "commerce_ai.adapters.cache",
        "commerce_ai.adapters.llm",
        "commerce_ai.adapters.session",
        "commerce_ai.api",
    ):
        imported = importlib.import_module(module_name)
        assert imported is not None

    for rel_init in (
        "src/commerce_ai/__init__.py",
        "src/commerce_ai/config/__init__.py",
        "src/commerce_ai/domain/__init__.py",
        "src/commerce_ai/agent/__init__.py",
        "src/commerce_ai/adapters/__init__.py",
        "src/commerce_ai/adapters/catalog/__init__.py",
        "src/commerce_ai/adapters/cache/__init__.py",
        "src/commerce_ai/adapters/llm/__init__.py",
        "src/commerce_ai/adapters/session/__init__.py",
        "src/commerce_ai/api/__init__.py",
        "tests/__init__.py",
        "tests/unit/__init__.py",
        "tests/integration/__init__.py",
    ):
        assert (BACKEND_DIR / rel_init).is_file(), f"Missing scaffold file: {rel_init}"

    pyproject = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    assert project["requires-python"] == ">=3.11"

    runtime_pkg_names = {
        re.split(r"[<>=\[!;\s]", dep.strip().lower(), maxsplit=1)[0]
        for dep in project["dependencies"]
    }
    for pkg in (
        "pydantic",
        "pydantic-settings",
        "httpx",
        "redis",
        "fastapi",
        "uvicorn",
        "langgraph",
        "sqlalchemy",
        "aiosqlite",
        "asyncpg",
    ):
        assert pkg in runtime_pkg_names

    for forbidden_sdk in ("litellm", "google-genai", "openai", "groq", "boto3"):
        assert forbidden_sdk not in runtime_pkg_names

    dev_deps = " ".join(pyproject["dependency-groups"]["dev"]).lower()
    for pkg in ("pytest", "pytest-asyncio", "fakeredis", "ruff", "mypy"):
        assert pkg in dev_deps

    pytest_cfg = pyproject["tool"]["pytest"]["ini_options"]
    assert pytest_cfg["asyncio_mode"] == "auto"
    assert pytest_cfg["addopts"] == ["-m", "not live"]
    assert any(marker.startswith("live:") for marker in pytest_cfg["markers"])


def test_scoring_config_defaults_and_overrides() -> None:
    """T1.2 — ScoringConfig defaults and valid custom overrides."""
    default_cfg = ScoringConfig()
    assert default_cfg.price_weight == 0.55
    assert default_cfg.rating_weight == 0.45
    assert default_cfg.bayesian_prior_count == 25
    assert default_cfg.bayesian_prior_mean == 4.0
    assert default_cfg.unrated_prior_rating == 3.4
    assert default_cfg.price_floor_ratio == 0.15
    assert default_cfg.price_ceiling_ratio == 3.0
    assert default_cfg.min_candidates_for_outlier_guard == 3
    assert default_cfg.top_k == 3

    custom_cfg = ScoringConfig(price_weight=0.70, rating_weight=0.30, top_k=2)
    assert custom_cfg.price_weight == 0.70
    assert custom_cfg.rating_weight == 0.30
    assert custom_cfg.top_k == 2


def test_market_registry_entries() -> None:
    """T1.3 — MARKET_REGISTRY maps EG, SA, AE to currency, gl, domains, and prefixes."""
    assert set(MARKET_REGISTRY.keys()) == {CountryCode.EG, CountryCode.SA, CountryCode.AE}

    eg = MARKET_REGISTRY[CountryCode.EG]
    assert isinstance(eg, MarketConfig)
    assert eg.currency is CurrencyCode.EGP
    assert eg.serper_gl == "eg"
    assert "amazon.eg" in eg.amazon_domains
    assert eg.noon_host == "noon.com"
    assert "/egypt" in eg.noon_path_prefixes
    assert "google.com.eg" in eg.google_shopping_domains

    sa = MARKET_REGISTRY[CountryCode.SA]
    assert sa.currency is CurrencyCode.SAR
    assert sa.serper_gl == "sa"
    assert "amazon.sa" in sa.amazon_domains
    assert "/saudi" in sa.noon_path_prefixes
    assert "google.com.sa" in sa.google_shopping_domains

    ae = MARKET_REGISTRY[CountryCode.AE]
    assert ae.currency is CurrencyCode.AED
    assert ae.serper_gl == "ae"
    assert "amazon.ae" in ae.amazon_domains
    assert "/uae" in ae.noon_path_prefixes
    assert "google.ae" in ae.google_shopping_domains


def test_app_settings_defaults_and_env_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T1.2 — AppSettings defaults, Phase 2 fields, CORS parsing, and .env.example loading."""
    for env_var in (
        "APP_ENV",
        "LOG_LEVEL",
        "SERPER_API_KEY",
        "REDIS_URL",
        "CATALOG_MODE",
        "CACHE_TTL_SECONDS",
        "SERPER_TIMEOUT_SECONDS",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "LLM_MODE",
        "EXPLAIN_MODE",
        "LLM_PRIMARY_MODEL",
        "LLM_FALLBACK_MODEL",
        "LLM_TIMEOUT_SECONDS",
        "GUARDRAIL_MAX_CHARS",
        "DATABASE_URL",
        "SESSION_TTL_SECONDS",
        "SESSION_MAX_TURNS",
        "CORS_ALLOWED_ORIGINS",
        "RATE_LIMIT_RPM",
        "TRUSTED_PROXY_CIDRS",
    ):
        monkeypatch.delenv(env_var, raising=False)

    defaults = AppSettings(_env_file=None)
    assert defaults.app_env == "development"
    assert defaults.log_level == "INFO"
    assert defaults.catalog_mode == "auto"
    assert defaults.cache_ttl_seconds == 1800
    assert defaults.serper_timeout_seconds == 2.0
    assert defaults.serper_api_key is None
    assert defaults.redis_url is None
    assert defaults.scoring == ScoringConfig()
    assert defaults.gemini_api_key is None
    assert defaults.groq_api_key is None
    assert defaults.openai_api_key is None
    assert defaults.llm_mode == "auto"
    assert defaults.explain_mode == "auto"
    assert defaults.llm_primary_model == "gemini/gemini-2.5-flash"
    assert defaults.llm_fallback_model == "groq/llama-3.3-70b-versatile"
    assert defaults.llm_timeout_seconds == 8.0
    assert defaults.guardrail_max_chars == 1000
    assert defaults.database_url == "sqlite+aiosqlite:///./commerce_ai.db"
    assert defaults.session_ttl_seconds == 86400
    assert defaults.session_max_turns == 10
    assert defaults.cors_allowed_origins == ["http://localhost:3000"]
    assert defaults.rate_limit_rpm == 60
    assert defaults.trusted_proxy_cidrs == ["127.0.0.1/32", "::1/128"]
    assert defaults.safe_summary()["trusted_proxy_cidrs"] == ["127.0.0.1/32", "::1/128"]

    env_copy = tmp_path / ".env"
    example_text = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")
    env_text = (
        example_text.replace("SERPER_API_KEY=", "SERPER_API_KEY=test-key-xyz   # inline note")
        .replace("GEMINI_API_KEY=", "GEMINI_API_KEY=gem-key-abc   # gemini note")
        .replace(
            "CORS_ALLOWED_ORIGINS=http://localhost:3000",
            "CORS_ALLOWED_ORIGINS=http://localhost:3000, https://shop.example.com  # origins",
        )
        .replace(
            "DATABASE_URL=sqlite+aiosqlite:///./commerce_ai.db",
            "DATABASE_URL=postgresql+asyncpg://commerce:dbsecret@postgres:5432/commerce_ai",
        )
    )
    env_copy.write_text(env_text, encoding="utf-8")

    loaded = AppSettings(_env_file=env_copy)
    assert loaded.app_env == "development"
    assert loaded.log_level == "INFO"
    assert loaded.catalog_mode == "auto"
    assert loaded.cache_ttl_seconds == 1800
    assert loaded.serper_timeout_seconds == 2.0
    assert loaded.redis_url is None
    assert loaded.serper_api_key is not None
    assert loaded.serper_api_key.get_secret_value() == "test-key-xyz"
    assert loaded.gemini_api_key is not None
    assert loaded.gemini_api_key.get_secret_value() == "gem-key-abc"
    assert loaded.cors_allowed_origins == ["http://localhost:3000", "https://shop.example.com"]
    assert loaded.database_url == "postgresql+asyncpg://commerce:dbsecret@postgres:5432/commerce_ai"
    assert "test-key-xyz" not in repr(loaded)
    assert "test-key-xyz" not in str(loaded)
    assert "gem-key-abc" not in repr(loaded)
    assert "dbsecret" not in repr(loaded)
    assert "dbsecret" not in str(loaded)
    assert "dbsecret" not in str(loaded.model_dump())
    assert "dbsecret" not in loaded.model_dump_json()

    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        '["http://localhost:3000", "https://admin.example.com"]  # json array',
    )
    json_cors_settings = AppSettings(_env_file=None)
    assert json_cors_settings.cors_allowed_origins == [
        "http://localhost:3000",
        "https://admin.example.com",
    ]

    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8, 192.168.1.5")
    csv_proxy_settings = AppSettings(_env_file=None)
    assert csv_proxy_settings.trusted_proxy_cidrs == ["10.0.0.0/8", "192.168.1.5/32"]

    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", '["172.16.0.0/12", "::1/128"]')
    json_proxy_settings = AppSettings(_env_file=None)
    assert json_proxy_settings.trusted_proxy_cidrs == ["172.16.0.0/12", "::1/128"]


def test_domain_error_hierarchy() -> None:
    """T1.5 — Domain exceptions preserve hierarchy and CatalogProviderError signature."""
    assert issubclass(OfferValidationError, DomainError)
    assert issubclass(OfferValidationError, ValueError)
    assert issubclass(CatalogProviderError, DomainError)
    assert issubclass(CacheStoreError, DomainError)

    err = CatalogProviderError(provider="serper", retriable=True, reason="timeout")
    assert err.provider == "serper"
    assert err.retriable is True
    assert err.reason == "timeout"
    assert "serper" in str(err)
    assert "timeout" in str(err)


def test_domain_enums() -> None:
    """T1.6 — StrEnum members expose exact uppercase names and expected values."""
    assert [m.name for m in CountryCode] == ["EG", "SA", "AE"]
    assert (CountryCode.EG, CountryCode.SA, CountryCode.AE) == ("EG", "SA", "AE")

    assert [m.name for m in CurrencyCode] == ["EGP", "SAR", "AED"]
    assert (CurrencyCode.EGP, CurrencyCode.SAR, CurrencyCode.AED) == ("EGP", "SAR", "AED")

    assert [m.name for m in StoreId] == ["NOON", "AMAZON"]
    assert (StoreId.NOON, StoreId.AMAZON) == ("noon", "amazon")

    assert [m.name for m in StoreFilter] == ["NOON", "AMAZON", "BOTH"]
    assert (StoreFilter.NOON, StoreFilter.AMAZON, StoreFilter.BOTH) == ("noon", "amazon", "both")

    assert [m.name for m in CatalogSourceMode] == ["SEED", "LIVE"]
    assert (CatalogSourceMode.SEED, CatalogSourceMode.LIVE) == ("seed", "live")


def test_product_offer_valid_price_and_currency_pairing() -> None:
    """T1.7 — ProductOffer accepts EG/SA/AE offers, quantizes price, validates rating/reviews."""
    eg_offer = ProductOffer.model_validate(_make_offer_payload(price=Decimal("1499.5")))
    assert eg_offer.price == Decimal("1499.50")

    sa_offer = ProductOffer.model_validate(
        _make_offer_payload(
            offer_id="offer-sa-1",
            price="299.994",
            currency=CurrencyCode.SAR,
            country=CountryCode.SA,
            store=StoreId.NOON,
            url="https://www.noon.com/saudi-ar/item-1",
            rating=None,
            review_count=0,
        )
    )
    assert sa_offer.price == Decimal("299.99")
    assert sa_offer.rating is None
    assert sa_offer.review_count == 0

    ae_offer = ProductOffer.model_validate(
        _make_offer_payload(
            offer_id="offer-ae-1",
            price=Decimal("899"),
            currency=CurrencyCode.AED,
            country=CountryCode.AE,
            store=StoreId.AMAZON,
            url="https://www.amazon.ae/dp/B0AE1234",
            rating=5.0,
            review_count=12,
        )
    )
    assert ae_offer.price == Decimal("899.00")


def test_product_offer_accepts_regional_and_attributed_google_urls() -> None:
    """T1.8 — Direct regional Noon/Amazon URLs and attributed Google Shopping links succeed."""
    direct_cases = [
        (CountryCode.EG, CurrencyCode.EGP, StoreId.AMAZON, "https://www.amazon.eg/dp/B001"),
        (CountryCode.EG, CurrencyCode.EGP, StoreId.NOON, "https://www.noon.com/egypt-en/item/1"),
        (CountryCode.SA, CurrencyCode.SAR, StoreId.AMAZON, "https://amazon.sa/dp/B002"),
        (CountryCode.SA, CurrencyCode.SAR, StoreId.NOON, "https://noon.com/saudi-ar/item/2"),
        (CountryCode.AE, CurrencyCode.AED, StoreId.AMAZON, "https://www.amazon.ae/dp/B003"),
        (CountryCode.AE, CurrencyCode.AED, StoreId.NOON, "https://www.noon.com/uae-en/item/3"),
    ]
    for country, currency, store, url in direct_cases:
        validated = validate_regional_offer_url(url, country=country, store=store)
        assert validated == url
        offer = ProductOffer.model_validate(
            _make_offer_payload(country=country, currency=currency, store=store, url=url)
        )
        assert str(offer.url) == url

    google_amazon_eg = ProductOffer.model_validate(
        _make_offer_payload(url="https://www.google.com/shopping/product/123"),
        context={"merchant_attribution": "Amazon.eg"},
    )
    assert str(google_amazon_eg.url) == "https://www.google.com/shopping/product/123"

    google_noon_eg = validate_regional_offer_url(
        "https://www.google.com.eg/shopping/product/123",
        country=CountryCode.EG,
        store=StoreId.NOON,
        merchant_attribution="Noon Egypt",
    )
    assert google_noon_eg == "https://www.google.com.eg/shopping/product/123"


def test_search_intent_normalized_cache_key() -> None:
    """T1.3 — SearchIntent Arabic folding, catalog_cache_key(), and normalized_cache_key()."""
    ar_a = SearchIntent(query="  سماعة   أنكر! ", country=CountryCode.EG)
    ar_b = SearchIntent(query="سَمَاعَةُ أنْكَر", country=CountryCode.EG)
    ar_c = SearchIntent(query="سماعه انكر", country=CountryCode.EG)
    assert ar_a.catalog_cache_key() == ar_b.catalog_cache_key() == ar_c.catalog_cache_key()
    assert ar_a.catalog_cache_key() == "eg:both:ar:سماعه-انكر"
    assert ar_a.normalized_cache_key() == ar_b.normalized_cache_key() == ar_c.normalized_cache_key()
    assert ar_a.normalized_cache_key() == "eg:both:ar:سماعه-انكر:none:none"

    ortho_a = SearchIntent(query="مكواة إلى أين آلة ٱختبار مبنى", country=CountryCode.EG)
    ortho_b = SearchIntent(query="مكواه الي اين اله اختبار مبني", country=CountryCode.EG)
    assert ortho_a.catalog_cache_key() == ortho_b.catalog_cache_key()

    digits_ar = SearchIntent(query="أيفون ١٥", country=CountryCode.EG)
    digits_fa = SearchIntent(query="ايفون ۱۵", country=CountryCode.EG)
    digits_en = SearchIntent(query="ايفون 15", country=CountryCode.EG)
    assert digits_ar.catalog_cache_key() == digits_en.catalog_cache_key()
    assert digits_fa.catalog_cache_key() == digits_en.catalog_cache_key()

    tatweel_ar = SearchIntent(query="سـمـاعـة أنـكـر", country=CountryCode.EG)
    assert tatweel_ar.catalog_cache_key() == ar_a.catalog_cache_key()

    en_a = SearchIntent(
        query=" Anker  Earbuds ",
        country=CountryCode.SA,
        store=StoreFilter.AMAZON,
        max_budget=Decimal("500"),
        min_rating=4.5,
        language="en",
    )
    en_b = SearchIntent(
        query="anker, earbuds!",
        country=CountryCode.SA,
        store=StoreFilter.AMAZON,
        max_budget=Decimal("500.00"),
        min_rating=4.5,
        language="en",
    )
    assert en_a.catalog_cache_key() == en_b.catalog_cache_key() == "sa:amazon:en:anker-earbuds"
    assert en_a.normalized_cache_key() == en_b.normalized_cache_key()
    assert en_a.normalized_cache_key() == "sa:amazon:en:anker-earbuds:500.00:4.50"

    zero_rating_intent = SearchIntent(
        query="Mouse",
        country=CountryCode.AE,
        min_rating=0.0,
        language="en",
    )
    assert zero_rating_intent.normalized_cache_key() == "ae:both:en:mouse:none:0.00"

    punct_key_a = SearchIntent(query="!!!", country=CountryCode.EG).normalized_cache_key()
    punct_key_b = SearchIntent(query="???", country=CountryCode.EG).normalized_cache_key()
    assert punct_key_a.startswith("eg:both:ar:q-")
    assert len(punct_key_a.split(":")[3]) == 10
    assert punct_key_a.endswith(":none:none")
    assert punct_key_a != punct_key_b


def test_phase2_domain_models_and_enums() -> None:
    """T1.4 — Phase 2 enums and models validate defaults and JSON round-trips."""
    assert [m.value for m in TurnAction] == ["search", "compare", "clarify", "off_topic", "refuse"]
    assert [m.value for m in TurnStatus] == ["ok", "clarify", "off_topic", "refused", "degraded"]

    msg = LLMMessage(role="user", content="سماعة أنكر")
    req = LLMRequest(messages=(msg,))
    assert req.max_tokens == 350
    assert req.temperature == 0.0
    assert req.json_mode is False
    assert req.task_name == "general"

    resp = LLMResponse(content='{"action":"search"}', provider="gemini", model="gemini-2.5-flash")
    assert resp.used_fallback_model is False

    google_offer = ProductOffer.model_validate(
        _make_offer_payload(url="https://www.google.com/shopping/product/123"),
        context={"merchant_attribution": "Amazon.eg"},
    )
    ranked_offer = RankedOffer(
        rank=1,
        offer=google_offer,
        value_score=91.5,
        price_norm=0.9,
        bayesian_rating=4.6,
        match_reasons=("best_overall_value",),
    )
    intent = SearchIntent(query="سماعة أنكر", country=CountryCode.EG, language="ar")
    session_state = SessionState(
        session_id="sess-1",
        market=CountryCode.EG,
        last_intent=intent,
        last_ranked_offers=[ranked_offer],
        turns=[
            SessionTurn(
                role="user",
                content="سماعة أنكر",
                action=TurnAction.SEARCH,
                created_at_iso="2026-11-15T12:00:00Z",
            )
        ],
        updated_at_epoch=1234.5,
    )
    session_json = session_state.model_dump_json()
    with pytest.raises(ValidationError):
        SessionState.model_validate_json(session_json)

    restored_session = SessionState.model_validate_json(
        session_json,
        context={"allow_verified_google_shopping_from_cache": True},
    )
    assert restored_session.session_id == "sess-1"
    assert restored_session.last_ranked_offers[0].offer.url == (
        "https://www.google.com/shopping/product/123"
    )

    telemetry = TurnTelemetry(llm_calls=1, catalog_called=True, catalog_cache_hit=False)
    turn_result = ChatTurnResult(
        session_id="sess-1",
        status=TurnStatus.OK,
        reply="إليك أفضل ٣ عروض",
        action=TurnAction.SEARCH,
        active_intent=intent,
        top_offers=[ranked_offer],
        telemetry=telemetry,
    )
    restored_turn = ChatTurnResult.model_validate_json(
        turn_result.model_dump_json(),
        context={"allow_verified_google_shopping_from_cache": True},
    )
    assert restored_turn == turn_result


def test_phase2_errors_and_ports() -> None:
    """T1.5 — LLMProviderError, SessionStoreError, and @runtime_checkable Phase 2 ports."""
    assert issubclass(LLMProviderError, DomainError)
    assert issubclass(SessionStoreError, DomainError)

    err = LLMProviderError(provider="gemini", retriable=True, reason="rate limited")
    assert err.provider == "gemini"
    assert err.retriable is True
    assert err.reason == "rate limited"
    assert str(err) == "[gemini] (retriable=True): rate limited"

    class _DummyLLM:
        async def complete(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(content="ok", provider="dummy", model="dummy-1")

    class _DummySessionRepo:
        async def get_session(self, session_id: str) -> SessionState | None:
            return None

        async def save_session(self, state: SessionState, ttl_seconds: int = 86400) -> None:
            return None

        async def delete_session(self, session_id: str) -> None:
            return None

    assert isinstance(_DummyLLM(), LLMClient)
    assert isinstance(_DummySessionRepo(), SessionRepository)


def test_ranking_and_catalog_result_models() -> None:
    """T1.10 — RankedOffer, RankingResult, and CatalogSearchResult validate and round-trip JSON."""
    offer = ProductOffer.model_validate(_make_offer_payload())
    ranked = RankedOffer(
        rank=1,
        offer=offer,
        value_score=91.25,
        price_norm=0.85,
        bayesian_rating=4.62,
        match_reasons=("best_overall_value", "high_review_confidence"),
    )
    ranking_result = RankingResult(
        ranked_offers=[ranked],
        total_candidates=4,
        filtered_accessories_count=1,
        filtered_outliers_count=1,
        degraded_fewer_than_k=True,
    )
    restored_ranking = RankingResult.model_validate_json(ranking_result.model_dump_json())
    assert restored_ranking == ranking_result

    catalog_result = CatalogSearchResult(
        offers=[offer],
        source_mode=CatalogSourceMode.SEED,
        cache_hit=False,
    )
    restored_catalog = CatalogSearchResult.model_validate_json(catalog_result.model_dump_json())
    assert restored_catalog == catalog_result


def test_hexagonal_boundary_no_vendor_imports() -> None:
    """T1.15 — config/, domain/, and agent/ import zero vendor or adapter packages."""
    forbidden = {
        "httpx",
        "redis",
        "serper",
        "langfuse",
        "boto3",
        "sqlalchemy",
        "fastapi",
        "litellm",
        "openai",
        "groq",
        "google",
    }
    target_dirs = [
        BACKEND_DIR / "src" / "commerce_ai" / "config",
        BACKEND_DIR / "src" / "commerce_ai" / "domain",
        BACKEND_DIR / "src" / "commerce_ai" / "agent",
    ]
    for directory in target_dirs:
        for py_file in directory.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top_pkg = alias.name.split(".")[0]
                        assert top_pkg not in forbidden, f"{py_file} imports {alias.name}"
                        assert not alias.name.startswith("commerce_ai.adapters")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    top_pkg = node.module.split(".")[0]
                    assert top_pkg not in forbidden, f"{py_file} imports {node.module}"
                    assert not node.module.startswith("commerce_ai.adapters")


def test_scoring_config_rejects_invalid_bounds() -> None:
    """T3.1 — ScoringConfig rejects invalid weight sums, negative values, and bad ratios."""
    invalid_kwargs: list[dict[str, object]] = [
        {"price_weight": 0.6, "rating_weight": 0.6},
        {"price_weight": -0.1, "rating_weight": 1.1},
        {"bayesian_prior_count": 0},
        {"bayesian_prior_mean": 5.5},
        {"bayesian_prior_mean": -0.1},
        {"unrated_prior_rating": 5.1},
        {"price_floor_ratio": 0.0},
        {"price_floor_ratio": 1.0},
        {"price_ceiling_ratio": 1.0},
        {"top_k": 0},
        {"top_k": 4},
        {"min_candidates_for_outlier_guard": 0},
    ]
    for kwargs in invalid_kwargs:
        with pytest.raises(ValidationError):
            ScoringConfig(**kwargs)  # type: ignore[arg-type]


def test_market_registry_rejects_unknown_market_and_foreign_merchants() -> None:
    """T3.2 — MARKET_REGISTRY raises KeyError on unknown market and blocks foreign merchants."""
    with pytest.raises(KeyError):
        _ = MARKET_REGISTRY["US"]  # type: ignore[index]

    eg_market = MARKET_REGISTRY[CountryCode.EG]
    assert eg_market.matches_merchant_attribution(StoreId.AMAZON, "Amazon.eg") is True
    assert eg_market.matches_merchant_attribution(StoreId.NOON, "Noon Egypt") is True
    assert eg_market.matches_merchant_attribution(StoreId.AMAZON, "Amazon.com") is False
    assert eg_market.matches_merchant_attribution(StoreId.AMAZON, "Amazon.sa") is False
    assert eg_market.matches_merchant_attribution(StoreId.NOON, "Noon Saudi") is False
    assert eg_market.matches_merchant_attribution(StoreId.AMAZON, "Unknown Seller") is False


def test_app_settings_secret_masking_and_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T3.1 — AppSettings normalizes blanks, rejects bad bounds, and masks secrets/URLs."""
    monkeypatch.setenv("SERPER_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    monkeypatch.setenv("GROQ_API_KEY", "  # only comment")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "   ")
    monkeypatch.setenv("REDIS_URL", "   ")
    monkeypatch.setenv("CATALOG_MODE", "seed  # forced seed")

    settings = AppSettings(_env_file=None)
    assert settings.serper_api_key is None
    assert settings.gemini_api_key is None
    assert settings.groq_api_key is None
    assert settings.openai_api_key is None
    assert settings.llm_fallback_model is None
    assert settings.redis_url is None
    assert settings.catalog_mode == "seed"

    raw_redis = "redis://:redis-pass-secret@redis.internal:6379/0"
    raw_db = "postgresql+asyncpg://commerce:pg-pass-secret@db.internal:5432/commerce_ai"
    masked = AppSettings(
        _env_file=None,
        serper_api_key=SecretStr("super-serper-secret"),
        gemini_api_key=SecretStr("super-gemini-secret"),
        groq_api_key=SecretStr("super-groq-secret"),
        openai_api_key=SecretStr("super-openai-secret"),
        redis_url=raw_redis,
        database_url=raw_db,
    )
    assert masked.redis_url == raw_redis
    assert masked.database_url == raw_db

    for secret in (
        "super-serper-secret",
        "super-gemini-secret",
        "super-groq-secret",
        "super-openai-secret",
        "redis-pass-secret",
        "pg-pass-secret",
    ):
        assert secret not in repr(masked)
        assert secret not in str(masked)
        assert secret not in str(masked.model_dump())
        assert secret not in masked.model_dump_json()

    dumped = masked.model_dump()
    assert dumped["redis_url"] == "redis://:***@redis.internal:6379/0"
    assert (
        dumped["database_url"] == "postgresql+asyncpg://commerce:***@db.internal:5432/commerce_ai"
    )
    assert "***" in repr(masked)

    summary = masked.safe_summary()
    assert summary["serper_api_key"] == "***"
    assert summary["gemini_api_key"] == "***"
    assert summary["groq_api_key"] == "***"
    assert summary["openai_api_key"] == "***"
    assert summary["redis_url"] == "redis://:***@redis.internal:6379/0"
    assert (
        summary["database_url"] == "postgresql+asyncpg://commerce:***@db.internal:5432/commerce_ai"
    )
    assert "redis-pass-secret" not in str(summary)
    assert "pg-pass-secret" not in str(summary)

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, catalog_mode="invalid")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, cache_ttl_seconds=0)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, serper_timeout_seconds=-1.0)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, guardrail_max_chars=10)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, guardrail_max_chars=4001)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, session_max_turns=1)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, session_max_turns=51)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, rate_limit_rpm=-1)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, llm_timeout_seconds=0.0)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, session_ttl_seconds=0)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, database_url="   ")
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, llm_primary_model="")
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, trusted_proxy_cidrs=["not-a-valid-cidr"])

    bad_port_redacted = redact_url_password("redis://:sec-ret@127.0.0.1:badport/0")
    assert bad_port_redacted is not None
    assert "sec-ret" not in bad_port_redacted
    assert "***" in bad_port_redacted

    complex_pw_redacted = redact_url_password("redis://user:p@ss:w%40rd@127.0.0.1:6379/0")
    assert complex_pw_redacted is not None
    assert "p@ss" not in complex_pw_redacted
    assert "w%40rd" not in complex_pw_redacted

    query_redacted = redact_url_password(
        "redis://127.0.0.1:6379/0"
        "?password=qsecret&pass=psecret&token=tsecret"
        "&passwd=wsecret&pwd=xsecret&secret=ysecret"
        "&api_key=zsecret&api-key=asecret&db=0"
    )
    assert query_redacted is not None
    for secret_val in (
        "qsecret",
        "psecret",
        "tsecret",
        "wsecret",
        "xsecret",
        "ysecret",
        "zsecret",
        "asecret",
    ):
        assert secret_val not in query_redacted
    for key_name in ("password", "pass", "token", "passwd", "pwd", "secret", "api_key", "api-key"):
        assert f"{key_name}=***" in query_redacted
    assert "db=0" in query_redacted

    bad_port_query_redacted = redact_url_password(
        "redis://:p@ss:word@127.0.0.1:badport/0?token=toksecret"
    )
    assert bad_port_query_redacted is not None
    assert "p@ss:word" not in bad_port_query_redacted
    assert "toksecret" not in bad_port_query_redacted


def test_product_offer_rejects_invalid_price_and_rating() -> None:
    """T3.4 — ProductOffer rejects non-positive/tiny/non-finite prices and invalid ratings."""
    bad_prices: list[object] = [
        Decimal("0"),
        Decimal("-10.50"),
        Decimal("0.001"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("1e50"),
    ]
    for bad_price in bad_prices:
        with pytest.raises(ValidationError):
            ProductOffer.model_validate(_make_offer_payload(price=bad_price))

    with pytest.raises(OfferValidationError):
        _validate_positive_currency_decimal(Decimal("1e50"), field_name="price")

    for bad_rating in (-0.1, 5.1, float("nan")):
        with pytest.raises(ValidationError):
            ProductOffer.model_validate(_make_offer_payload(rating=bad_rating))

    with pytest.raises(ValidationError):
        ProductOffer.model_validate(_make_offer_payload(review_count=-1))


def test_product_offer_rejects_currency_mismatch() -> None:
    """T3.5 — ProductOffer rejects mismatched (country, currency) combinations."""
    mismatches = [
        (CountryCode.EG, CurrencyCode.SAR, "https://www.amazon.eg/dp/1"),
        (CountryCode.SA, CurrencyCode.EGP, "https://www.amazon.sa/dp/1"),
        (CountryCode.AE, CurrencyCode.EGP, "https://www.amazon.ae/dp/1"),
    ]
    for country, currency, url in mismatches:
        with pytest.raises(ValidationError):
            ProductOffer.model_validate(
                _make_offer_payload(country=country, currency=currency, url=url)
            )


def test_product_offer_rejects_cross_country_and_cross_store_urls() -> None:
    """T3.6 — ProductOffer rejects cross-country domains, bare noon paths, and store mismatches."""
    invalid_cases = [
        (CountryCode.EG, CurrencyCode.EGP, StoreId.AMAZON, "https://www.amazon.com/dp/1"),
        (CountryCode.EG, CurrencyCode.EGP, StoreId.AMAZON, "https://www.amazon.sa/dp/1"),
        (CountryCode.EG, CurrencyCode.EGP, StoreId.NOON, "https://www.noon.com/saudi-en/item"),
        (CountryCode.EG, CurrencyCode.EGP, StoreId.NOON, "https://www.noon.com/item"),
        (CountryCode.EG, CurrencyCode.EGP, StoreId.NOON, "https://www.amazon.eg/dp/1"),
        (CountryCode.SA, CurrencyCode.SAR, StoreId.AMAZON, "https://www.noon.com/saudi-en/item"),
    ]
    for country, currency, store, url in invalid_cases:
        with pytest.raises(ValidationError):
            ProductOffer.model_validate(
                _make_offer_payload(country=country, currency=currency, store=store, url=url)
            )


def test_product_offer_rejects_insecure_and_third_party_urls() -> None:
    """T3.7 — ProductOffer rejects non-HTTPS, malformed/traversal, control-char, & unknown URLs."""
    for bad_url in (
        "http://www.amazon.eg/dp/123",
        "ftp://www.amazon.eg/dp/123",
        "https://www.jumia.com.eg/product/123",
        "https://www.ebay.com/itm/123",
        "https://www.amazon.eg/dp/123\n",
        "https://www.amazon.eg/dp/123\t",
        " https://www.amazon.eg/dp/123 ",
        "https://www.amazon.eg/dp/123\x00",
        "https://www.amazon.eg\\dp\\123",
        "https://www.amazon.eg/dp/123;jsessionid=1",
        "https://www.amazon.eg/dp/../other",
        "https://[::1/bad",
    ):
        with pytest.raises(ValidationError):
            ProductOffer.model_validate(_make_offer_payload(url=bad_url))

    for bad_noon_url in (
        "https://www.noon.com/egyptian-evil/item",
        "https://www.noon.com/egypt-/item",
        "https://www.noon.com/egypt-en/../saudi-en/item",
        "https://www.noon.com/egypt-en/%2e%2e/saudi-en/item",
        "https://www.noon.com/egypt-en%2f../saudi-en/item",
        "https://www.noon.com/egypt-en/%5c../item",
    ):
        with pytest.raises(ValidationError):
            ProductOffer.model_validate(_make_offer_payload(store=StoreId.NOON, url=bad_noon_url))

    for bad_img in (
        "http://cdn.example.com/a.jpg",
        "not-a-url",
        "",
        "https://user:pass@cdn.example.com/a.jpg",
        "https://user@cdn.example.com/a.jpg",
        "https://cdn.example.com/a.jpg\n",
        " https://cdn.example.com/a.jpg",
        "https://[::1/bad",
    ):
        with pytest.raises(ValidationError):
            ProductOffer.model_validate(_make_offer_payload(image_url=bad_img))


def test_google_shopping_url_attribution_validation_and_cache_roundtrip() -> None:
    """T3.8 — Google Shopping URLs enforce attribution and cache JSON round-trips safely."""
    google_url = "https://www.google.com/shopping/product/123"

    with pytest.raises(OfferValidationError):
        validate_regional_offer_url(
            google_url,
            country=CountryCode.EG,
            store=StoreId.AMAZON,
            merchant_attribution=None,
        )

    with pytest.raises(ValidationError):
        ProductOffer.model_validate(_make_offer_payload(url=google_url))

    with pytest.raises(ValidationError):
        ProductOffer.model_validate(
            _make_offer_payload(url=google_url),
            context={"merchant_attribution": None},
        )

    with pytest.raises(ValidationError):
        ProductOffer.model_validate(
            _make_offer_payload(url=google_url),
            context={"merchant_attribution": "Unknown Seller"},
        )

    with pytest.raises(ValidationError):
        ProductOffer.model_validate(
            _make_offer_payload(url=google_url),
            context={"merchant_attribution": "Amazon.sa"},
        )

    with pytest.raises(ValidationError):
        ProductOffer.model_validate(
            _make_offer_payload(url="https://www.google.com.sa/shopping/product/123"),
            context={"merchant_attribution": "Amazon.eg"},
        )

    for bad_google_url in (
        "https://www.google.com/search?q=iphone",
        "https://www.google.com/shopping-evil/product/123",
        "https://www.google.com/shopping/../search?q=iphone",
    ):
        with pytest.raises(ValidationError):
            ProductOffer.model_validate(
                _make_offer_payload(url=bad_google_url),
                context={"merchant_attribution": "Amazon.eg"},
            )

    attributed_offer = ProductOffer.model_validate(
        _make_offer_payload(url=google_url),
        context={"merchant_attribution": "Amazon.eg"},
    )
    offer_json = attributed_offer.model_dump_json()
    with pytest.raises(ValidationError):
        ProductOffer.model_validate_json(offer_json)

    cached_payload = CatalogSearchResult(
        offers=[attributed_offer],
        source_mode=CatalogSourceMode.LIVE,
        cache_hit=False,
    ).model_dump_json()
    with pytest.raises(ValidationError):
        CatalogSearchResult.model_validate_json(cached_payload)
    with pytest.raises(ValidationError):
        CatalogSearchResult.model_validate_json(
            cached_payload,
            context={"allow_verified_google_shopping_from_cache": "yes"},
        )
    with pytest.raises(ValidationError):
        CatalogSearchResult.model_validate_json(
            cached_payload,
            context={
                "allow_verified_google_shopping_from_cache": True,
                "merchant_attribution": "ThirdParty",
            },
        )

    restored = CatalogSearchResult.model_validate_json(
        cached_payload,
        context={"allow_verified_google_shopping_from_cache": True},
    )
    assert restored.offers[0].url == google_url

    ranked_restored = RankedOffer(
        rank=1,
        offer=restored.offers[0],
        value_score=88.5,
        price_norm=0.75,
        bayesian_rating=4.5,
    )
    assert ranked_restored.offer.url == google_url

    tampered_search_json = cached_payload.replace("/shopping/product/123", "/search?q=iphone")
    with pytest.raises(ValidationError):
        CatalogSearchResult.model_validate_json(tampered_search_json)
    with pytest.raises(ValidationError):
        CatalogSearchResult.model_validate_json(
            tampered_search_json,
            context={"allow_verified_google_shopping_from_cache": True},
        )


def test_search_intent_validation_edge_cases() -> None:
    """T3.2 — SearchIntent separates ar/en, folds Arabic orthography, and hashes punctuation."""
    for bad_query in ("", "   "):
        with pytest.raises(ValidationError):
            SearchIntent(query=bad_query, country=CountryCode.EG)

    max_allowed = SearchIntent(
        query="AirPods", country=CountryCode.SA, max_budget=Decimal("10000000.00")
    )
    assert max_allowed.max_budget == Decimal("10000000.00")

    for bad_budget in (
        Decimal("0"),
        Decimal("-50"),
        Decimal("0.001"),
        Decimal("10000000.01"),
        Decimal("1e50"),
    ):
        with pytest.raises(ValidationError):
            SearchIntent(query="AirPods", country=CountryCode.SA, max_budget=bad_budget)

    for bad_rating in (-0.1, 5.1):
        with pytest.raises(ValidationError):
            SearchIntent(query="AirPods", country=CountryCode.AE, min_rating=bad_rating)

    ar_v1 = SearchIntent(
        query="  سَمَاعَةُ: أنْكَر؟! ",
        country=CountryCode.EG,
        store=StoreFilter.NOON,
        language="ar",
    )
    ar_v2 = SearchIntent(
        query="سماعه انكر",
        country=CountryCode.EG,
        store=StoreFilter.NOON,
        language="ar",
    )
    assert ar_v1.catalog_cache_key() == ar_v2.catalog_cache_key()
    assert ar_v1.normalized_cache_key() == ar_v2.normalized_cache_key()

    en_same_query = SearchIntent(
        query="سماعه انكر",
        country=CountryCode.EG,
        store=StoreFilter.NOON,
        language="en",
    )
    assert en_same_query.catalog_cache_key() != ar_v2.catalog_cache_key()
    assert en_same_query.normalized_cache_key() != ar_v2.normalized_cache_key()

    punct_a = SearchIntent(query="...", country=CountryCode.EG).catalog_cache_key()
    punct_b = SearchIntent(query="---", country=CountryCode.EG).catalog_cache_key()
    assert punct_a.startswith("eg:both:ar:q-")
    assert punct_a != punct_b


def test_phase2_models_reject_invalid_bounds() -> None:
    """T3.3 — Phase 2 domain models reject invalid bounds and extra fields."""
    valid_msg = LLMMessage(role="user", content="hello")
    with pytest.raises(ValidationError):
        LLMRequest(messages=())
    with pytest.raises(ValidationError):
        LLMRequest(messages=(valid_msg,), max_tokens=0)
    with pytest.raises(ValidationError):
        LLMRequest(messages=(valid_msg,), max_tokens=1025)
    with pytest.raises(ValidationError):
        LLMRequest(messages=(valid_msg,), temperature=1.1)
    with pytest.raises(ValidationError):
        TurnTelemetry(llm_calls=3)
    with pytest.raises(ValidationError):
        TurnTelemetry(llm_calls=-1)
    with pytest.raises(ValidationError):
        SessionState(session_id="   ")

    with pytest.raises(ValidationError):
        LLMMessage(role="user", content="hi", extra_field="bad")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        LLMRequest(messages=(valid_msg,), extra_field="bad")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        LLMResponse(
            content="ok",
            provider="gemini",
            model="m",
            extra_field="bad",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        SessionTurn(
            role="user",
            content="hi",
            created_at_iso="2026-11-15T12:00:00Z",
            extra_field="bad",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        TurnTelemetry(extra_field="bad")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ChatTurnResult(
            session_id="s1",
            status=TurnStatus.OK,
            reply="ok",
            action=TurnAction.SEARCH,
            telemetry=TurnTelemetry(),
            extra_field="bad",  # type: ignore[call-arg]
        )


def test_ranked_offer_rejects_out_of_bounds() -> None:
    """T3.10 — RankedOffer and RankingResult reject out-of-range scores, ranks, and counts."""
    offer = ProductOffer.model_validate(_make_offer_payload())
    for bad_rank in (0, 4):
        with pytest.raises(ValidationError):
            RankedOffer(
                rank=bad_rank,
                offer=offer,
                value_score=80.0,
                price_norm=0.5,
                bayesian_rating=4.2,
            )

    for field_name, bad_val in (
        ("value_score", -0.1),
        ("value_score", 100.1),
        ("price_norm", -0.01),
        ("price_norm", 1.01),
        ("bayesian_rating", -0.1),
        ("bayesian_rating", 5.01),
    ):
        kwargs: dict[str, object] = {
            "rank": 1,
            "offer": offer,
            "value_score": 80.0,
            "price_norm": 0.5,
            "bayesian_rating": 4.2,
        }
        kwargs[field_name] = bad_val
        with pytest.raises(ValidationError):
            RankedOffer(**kwargs)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        RankingResult(
            ranked_offers=[],
            total_candidates=-1,
            filtered_accessories_count=0,
            filtered_outliers_count=0,
            degraded_fewer_than_k=True,
        )


def test_env_example_and_pii_exclusion() -> None:
    """T3.11 — .env.example has zero secrets, .gitignore ignores secrets/caches, no PII."""
    env_example = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")
    for secret_key in (
        "SERPER_API_KEY",
        "REDIS_URL",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ):
        matching_lines = [
            line.strip()
            for line in env_example.splitlines()
            if line.strip().startswith(f"{secret_key}=")
        ]
        assert len(matching_lines) == 1
        assert matching_lines[0] == f"{secret_key}="

    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (
        ".env",
        ".env.*",
        "!.env.example",
        "__pycache__/",
        "*.py[cod]",
        ".venv/",
        "*.db",
        ".pytest_cache/",
        ".ruff_cache/",
        ".mypy_cache/",
        "*.egg-info/",
    ):
        assert pattern in gitignore

    pii_and_payment_fields = {
        "card_number",
        "cvv",
        "expiry",
        "iban",
        "password",
        "email",
        "phone",
        "ssn",
        "national_id",
        "passport",
        "address",
    }
    assert set(ProductOffer.model_fields.keys()).isdisjoint(pii_and_payment_fields)
    assert set(SearchIntent.model_fields.keys()).isdisjoint(pii_and_payment_fields)
