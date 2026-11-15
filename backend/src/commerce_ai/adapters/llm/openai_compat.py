"""Async httpx adapter for OpenAI-compatible chat completions (Groq, OpenAI, vLLM/Ollama)."""

import logging
import time
from typing import Any

import httpx
from pydantic import SecretStr

from commerce_ai.domain.errors import LLMProviderError
from commerce_ai.domain.models import LLMRequest, LLMResponse

_PROVIDER_DEFAULT_BASE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
}

logger = logging.getLogger(__name__)


def _resolve_provider_and_model(
    model: str,
    provider: str | None,
    base_url: str | None,
) -> tuple[str, str, str]:
    cleaned_model = model.strip()
    if not cleaned_model:
        raise LLMProviderError(
            provider=provider or "openai",
            retriable=False,
            reason="LLM model identifier must not be empty",
        )

    explicit_provider = provider.strip().lower() if provider is not None else None
    resolved_provider = explicit_provider
    model_id = cleaned_model

    if "/" in cleaned_model:
        prefix, remainder = cleaned_model.split("/", 1)
        norm_prefix = prefix.strip().lower()
        if norm_prefix in _PROVIDER_DEFAULT_BASE_URLS and (
            explicit_provider is None or explicit_provider == norm_prefix
        ):
            resolved_provider = norm_prefix
            model_id = remainder.strip()
        elif explicit_provider is not None and norm_prefix == explicit_provider:
            model_id = remainder.strip()

    if not model_id:
        raise LLMProviderError(
            provider=resolved_provider or "openai",
            retriable=False,
            reason="LLM model identifier must not be empty",
        )

    if resolved_provider is None:
        resolved_provider = "openai"

    if base_url is not None:
        resolved_base_url = base_url.strip().rstrip("/")
    elif resolved_provider in _PROVIDER_DEFAULT_BASE_URLS:
        resolved_base_url = _PROVIDER_DEFAULT_BASE_URLS[resolved_provider]
    else:
        raise LLMProviderError(
            provider=resolved_provider,
            retriable=False,
            reason=f"base_url is required for OpenAI-compatible provider {resolved_provider!r}",
        )

    if not resolved_base_url:
        raise LLMProviderError(
            provider=resolved_provider,
            retriable=False,
            reason="base_url must not be empty",
        )

    return resolved_provider, model_id, resolved_base_url


def _extract_non_neg_int(mapping: dict[str, Any], key: str) -> int:
    raw = mapping.get(key, 0)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return max(0, raw)
    return 0


class OpenAICompatibleLLMClient:
    """Async httpx LLMClient targeting OpenAI-compatible /chat/completions endpoints."""

    def __init__(
        self,
        api_key: SecretStr,
        *,
        model: str = "gpt-4o-mini",
        provider: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 8.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        resolved_provider, model_id, resolved_base_url = _resolve_provider_and_model(
            model=model,
            provider=provider,
            base_url=base_url,
        )
        if not api_key.get_secret_value().strip():
            raise LLMProviderError(
                provider=resolved_provider,
                retriable=False,
                reason=f"API key for provider {resolved_provider!r} must not be empty",
            )
        if timeout_seconds <= 0:
            raise LLMProviderError(
                provider=resolved_provider,
                retriable=False,
                reason="timeout_seconds must be positive",
            )

        self._api_key = api_key
        self._provider = resolved_provider
        self._model_id = model_id
        self._base_url = resolved_base_url
        self._timeout_seconds = timeout_seconds
        self._client = http_client
        self._owns_client = http_client is None

    def _redact(self, text: str) -> str:
        secret = self._api_key.get_secret_value()
        return text.replace(secret, "***") if secret else text

    async def _post_chat_completions(self, payload: dict[str, Any]) -> httpx.Response:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_seconds)
            self._owns_client = True
        return await self._client.post(
            url,
            json=payload,
            headers=headers,
            timeout=self._timeout_seconds,
        )

    async def aclose(self) -> None:
        """Close internally owned httpx.AsyncClient if created."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute one bounded /chat/completions request."""
        payload: dict[str, Any] = {
            "model": self._model_id,
            "messages": [
                {"role": message.role, "content": message.content} for message in request.messages
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            response = await self._post_chat_completions(payload)
        except httpx.TimeoutException as exc:
            reason = self._redact(f"{self._provider} request timed out: {exc}")
            logger.warning("%s", reason)
            raise LLMProviderError(
                provider=self._provider,
                retriable=True,
                reason=reason,
            ) from exc
        except httpx.TransportError as exc:
            reason = self._redact(f"{self._provider} transport error: {exc}")
            logger.warning("%s", reason)
            raise LLMProviderError(
                provider=self._provider,
                retriable=True,
                reason=reason,
            ) from exc
        except httpx.HTTPError as exc:
            reason = self._redact(f"{self._provider} HTTP error: {exc}")
            logger.warning("%s", reason)
            raise LLMProviderError(
                provider=self._provider,
                retriable=False,
                reason=reason,
            ) from exc

        latency_ms = max(0.0, (time.perf_counter() - started) * 1000.0)

        if response.status_code < 200 or response.status_code >= 300:
            retriable = response.status_code == 429 or 500 <= response.status_code < 600
            reason = self._redact(f"{self._provider} API returned HTTP {response.status_code}")
            logger.warning("%s (retriable=%s)", reason, retriable)
            raise LLMProviderError(provider=self._provider, retriable=retriable, reason=reason)

        try:
            body: Any = response.json()
        except ValueError as exc:
            raise LLMProviderError(
                provider=self._provider,
                retriable=False,
                reason=f"{self._provider} API returned malformed JSON",
            ) from exc

        if not isinstance(body, dict):
            raise LLMProviderError(
                provider=self._provider,
                retriable=False,
                reason=f"{self._provider} API response must be a JSON object",
            )

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise LLMProviderError(
                provider=self._provider,
                retriable=False,
                reason=f"{self._provider} API response missing valid 'choices' list",
            )

        message_obj = choices[0].get("message")
        raw_content = message_obj.get("content") if isinstance(message_obj, dict) else None
        if not isinstance(raw_content, str) or not raw_content.strip():
            raise LLMProviderError(
                provider=self._provider,
                retriable=False,
                reason=f"{self._provider} API response missing text message content",
            )

        usage = body.get("usage")
        input_tokens = (
            _extract_non_neg_int(usage, "prompt_tokens") if isinstance(usage, dict) else 0
        )
        output_tokens = (
            _extract_non_neg_int(usage, "completion_tokens") if isinstance(usage, dict) else 0
        )

        raw_model = body.get("model")
        model_used = (
            raw_model.strip()
            if isinstance(raw_model, str) and raw_model.strip()
            else self._model_id
        )

        return LLMResponse(
            content=raw_content,
            provider=self._provider,
            model=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(latency_ms, 2),
            used_fallback_model=False,
        )
