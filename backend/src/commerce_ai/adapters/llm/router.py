"""Single-failover model router implementing the LLMClient port."""

import inspect
import logging

from commerce_ai.domain.errors import LLMProviderError
from commerce_ai.domain.models import LLMRequest, LLMResponse
from commerce_ai.domain.ports import LLMClient

logger = logging.getLogger(__name__)


async def _maybe_aclose(client: object | None) -> None:
    if client is None:
        return
    aclose = getattr(client, "aclose", None)
    if callable(aclose):
        result = aclose()
        if inspect.isawaitable(result):
            await result


class ModelRouterLLMClient:
    """LLMClient router executing primary first and failing over at most once to fallback."""

    def __init__(
        self,
        primary: LLMClient,
        fallback: LLMClient | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def primary(self) -> LLMClient:
        """Return the configured primary LLM client."""
        return self._primary

    @property
    def fallback(self) -> LLMClient | None:
        """Return the optional fallback LLM client."""
        return self._fallback

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Complete using primary, falling back at most once on LLMProviderError."""
        try:
            return await self._primary.complete(request)
        except LLMProviderError as exc:
            if self._fallback is None:
                raise
            logger.warning(
                "Primary LLM client failed (%s); falling back once to secondary model",
                exc,
            )
            fallback_response = await self._fallback.complete(request)
            return fallback_response.model_copy(update={"used_fallback_model": True})

    async def aclose(self) -> None:
        """Close underlying primary and fallback clients if they expose aclose()."""
        try:
            await _maybe_aclose(self._primary)
        finally:
            await _maybe_aclose(self._fallback)
