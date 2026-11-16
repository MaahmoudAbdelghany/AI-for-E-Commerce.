"""Async httpx adapter for Google Gemini generateContent API."""

import logging
import time
from typing import Any

import httpx
from pydantic import SecretStr

from commerce_ai.domain.errors import LLMProviderError
from commerce_ai.domain.models import LLMRequest, LLMResponse

GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

logger = logging.getLogger(__name__)


def _normalize_gemini_model_id(model: str) -> str:
    cleaned = model.strip()
    if cleaned.startswith("gemini/"):
        cleaned = cleaned.split("/", 1)[1].strip()
    if not cleaned:
        raise LLMProviderError(
            provider="gemini",
            retriable=False,
            reason="Gemini model identifier must not be empty",
        )
    return cleaned


def _extract_non_neg_int(mapping: dict[str, Any], key: str) -> int:
    raw = mapping.get(key, 0)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return max(0, raw)
    return 0


class GeminiLLMClient:
    """Async httpx LLMClient calling Gemini generateContent with header-only API key auth."""

    def __init__(
        self,
        api_key: SecretStr,
        *,
        model: str = "gemini-2.5-flash",
        timeout_seconds: float = 8.0,
        base_url: str = GEMINI_DEFAULT_BASE_URL,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.get_secret_value().strip():
            raise LLMProviderError(
                provider="gemini",
                retriable=False,
                reason="GEMINI_API_KEY must not be empty",
            )
        if timeout_seconds <= 0:
            raise LLMProviderError(
                provider="gemini",
                retriable=False,
                reason="timeout_seconds must be positive",
            )
        self._api_key = api_key
        self._model_id = _normalize_gemini_model_id(model)
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url.rstrip("/")
        self._client = http_client
        self._owns_client = http_client is None

    def _redact(self, text: str) -> str:
        secret = self._api_key.get_secret_value()
        return text.replace(secret, "***") if secret else text

    async def _post_generate_content(self, payload: dict[str, Any]) -> httpx.Response:
        url = f"{self._base_url}/models/{self._model_id}:generateContent"
        headers = {
            "x-goog-api-key": self._api_key.get_secret_value(),
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
        """Execute one bounded Gemini generateContent request."""
        system_parts: list[dict[str, str]] = []
        contents: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "system":
                if message.content.strip():
                    system_parts.append({"text": message.content})
                continue
            gemini_role = "model" if message.role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": message.content}]})

        if not contents and system_parts:
            contents.append({"role": "user", "parts": system_parts})
            system_parts = []

        generation_config: dict[str, Any] = {
            "maxOutputTokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.json_mode:
            generation_config["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}

        started = time.perf_counter()
        try:
            response = await self._post_generate_content(payload)
        except httpx.TimeoutException as exc:
            reason = self._redact(f"Gemini request timed out: {exc}")
            logger.warning("%s", reason)
            raise LLMProviderError(provider="gemini", retriable=True, reason=reason) from exc
        except httpx.TransportError as exc:
            reason = self._redact(f"Gemini transport error: {exc}")
            logger.warning("%s", reason)
            raise LLMProviderError(provider="gemini", retriable=True, reason=reason) from exc
        except httpx.HTTPError as exc:
            reason = self._redact(f"Gemini HTTP error: {exc}")
            logger.warning("%s", reason)
            raise LLMProviderError(provider="gemini", retriable=False, reason=reason) from exc

        latency_ms = max(0.0, (time.perf_counter() - started) * 1000.0)

        if response.status_code < 200 or response.status_code >= 300:
            retriable = response.status_code == 429 or 500 <= response.status_code < 600
            reason = self._redact(f"Gemini API returned HTTP {response.status_code}")
            logger.warning("%s (retriable=%s)", reason, retriable)
            raise LLMProviderError(provider="gemini", retriable=retriable, reason=reason)

        try:
            body: Any = response.json()
        except ValueError as exc:
            raise LLMProviderError(
                provider="gemini",
                retriable=False,
                reason="Gemini API returned malformed JSON",
            ) from exc

        if not isinstance(body, dict):
            raise LLMProviderError(
                provider="gemini",
                retriable=False,
                reason="Gemini API response must be a JSON object",
            )

        candidates = body.get("candidates")
        if (
            not isinstance(candidates, list)
            or not candidates
            or not isinstance(candidates[0], dict)
        ):
            raise LLMProviderError(
                provider="gemini",
                retriable=False,
                reason="Gemini API response missing valid 'candidates' list",
            )

        content_obj = candidates[0].get("content")
        parts = content_obj.get("parts") if isinstance(content_obj, dict) else None
        if not isinstance(parts, list):
            raise LLMProviderError(
                provider="gemini",
                retriable=False,
                reason="Gemini API candidate missing 'content.parts'",
            )

        text_segments = [
            part["text"]
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        combined_text = "".join(text_segments)
        if not combined_text.strip():
            raise LLMProviderError(
                provider="gemini",
                retriable=False,
                reason="Gemini API returned empty text content",
            )

        usage = body.get("usageMetadata")
        input_tokens = (
            _extract_non_neg_int(usage, "promptTokenCount") if isinstance(usage, dict) else 0
        )
        output_tokens = (
            _extract_non_neg_int(usage, "candidatesTokenCount") if isinstance(usage, dict) else 0
        )

        return LLMResponse(
            content=combined_text,
            provider="gemini",
            model=self._model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(latency_ms, 2),
            used_fallback_model=False,
        )
