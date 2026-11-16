"""Opt-in live LLM smoke test (deselected by default via `-m "not live"`)."""

import pytest

from commerce_ai.adapters.llm import create_llm_client
from commerce_ai.agent.intent import extract_turn_intent
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.errors import LLMProviderError
from commerce_ai.domain.models import CountryCode, TurnAction


def _has_secret(value: object) -> bool:
    if value is None:
        return False
    get_secret = getattr(value, "get_secret_value", None)
    if callable(get_secret):
        return bool(str(get_secret()).strip())
    return bool(str(value).strip())


@pytest.mark.live
async def test_live_llm_intent_extraction_smoke() -> None:
    """Exercise live LLM client factory and bounded intent extraction when keys exist."""
    settings = AppSettings()
    if settings.llm_mode == "fake":
        has_any_key = any(
            _has_secret(key)
            for key in (
                settings.gemini_api_key,
                settings.groq_api_key,
                settings.openai_api_key,
            )
        )
        if not has_any_key:
            pytest.skip("Live LLM smoke skipped: no live provider API key configured.")
        settings = settings.model_copy(update={"llm_mode": "live"})

    try:
        client = create_llm_client(settings)
    except LLMProviderError as exc:
        pytest.skip(f"Live LLM smoke skipped: {exc.reason}")

    if client is None:
        pytest.skip("Live LLM smoke skipped: no live provider API key configured.")
    result = await extract_turn_intent(
        "Anker earbuds in Egypt under 2500 EGP",
        default_country=CountryCode.EG,
        llm_client=client,
    )
    assert result.llm_calls_used == 1
    assert result.action == TurnAction.SEARCH
    assert result.intent is not None
    assert result.intent.country == CountryCode.EG
