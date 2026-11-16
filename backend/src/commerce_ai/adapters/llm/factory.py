"""Factory wiring AppSettings to FakeLLMClient, live routed LLMClient, or None."""

import httpx
from pydantic import SecretStr

from commerce_ai.adapters.llm.fake import FakeLLMClient
from commerce_ai.adapters.llm.gemini import GeminiLLMClient
from commerce_ai.adapters.llm.openai_compat import OpenAICompatibleLLMClient
from commerce_ai.adapters.llm.router import ModelRouterLLMClient
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.errors import LLMProviderError
from commerce_ai.domain.ports import LLMClient

_SUPPORTED_PROVIDERS = frozenset({"gemini", "groq", "openai"})


def _parse_model_spec(model_spec: str) -> tuple[str, str]:
    cleaned = model_spec.strip()
    if "/" not in cleaned:
        raise LLMProviderError(
            provider="llm",
            retriable=False,
            reason=f"Model spec {model_spec!r} must use '<provider>/<model>' format",
        )
    provider_raw, model_id = cleaned.split("/", 1)
    provider = provider_raw.strip().lower()
    model_name = model_id.strip()
    if provider not in _SUPPORTED_PROVIDERS or not model_name:
        raise LLMProviderError(
            provider="llm",
            retriable=False,
            reason=f"Unsupported LLM provider in model spec: {model_spec!r}",
        )
    return provider, model_name


def _api_key_for_provider(settings: AppSettings, provider: str) -> SecretStr | None:
    if provider == "gemini":
        key = settings.gemini_api_key
    elif provider == "groq":
        key = settings.groq_api_key
    elif provider == "openai":
        key = settings.openai_api_key
    else:
        return None
    if key is None or not key.get_secret_value().strip():
        return None
    return key


def _build_single_client(
    model_spec: str,
    settings: AppSettings,
    *,
    http_client: httpx.AsyncClient | None,
) -> LLMClient | None:
    provider, model_id = _parse_model_spec(model_spec)
    api_key = _api_key_for_provider(settings, provider)
    if api_key is None:
        return None

    if provider == "gemini":
        return GeminiLLMClient(
            api_key=api_key,
            model=model_id,
            timeout_seconds=settings.llm_timeout_seconds,
            http_client=http_client,
        )
    return OpenAICompatibleLLMClient(
        api_key=api_key,
        model=model_id,
        provider=provider,
        timeout_seconds=settings.llm_timeout_seconds,
        http_client=http_client,
    )


def create_llm_client(
    settings: AppSettings,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> LLMClient | None:
    """Resolve FakeLLMClient, routed live LLMClient, or None honoring settings.llm_mode."""
    if settings.llm_mode == "fake":
        return FakeLLMClient()

    if settings.llm_mode not in {"auto", "live"}:
        raise LLMProviderError(
            provider="llm",
            retriable=False,
            reason=f"Unsupported llm_mode: {settings.llm_mode!r}",
        )

    primary = _build_single_client(
        settings.llm_primary_model,
        settings,
        http_client=http_client,
    )
    fallback = (
        _build_single_client(
            settings.llm_fallback_model,
            settings,
            http_client=http_client,
        )
        if settings.llm_fallback_model is not None
        else None
    )

    if primary is not None:
        return ModelRouterLLMClient(primary=primary, fallback=fallback)

    if fallback is not None:
        return ModelRouterLLMClient(primary=fallback, fallback=None)

    if settings.llm_mode == "live":
        raise LLMProviderError(
            provider="llm",
            retriable=False,
            reason="LLM API key is required when llm_mode is 'live'",
        )
    return None
