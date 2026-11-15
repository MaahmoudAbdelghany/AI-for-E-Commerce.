"""100% offline deterministic FakeLLMClient for tests and offline execution."""

import inspect
from collections import deque
from collections.abc import Awaitable, Callable, Sequence

from commerce_ai.domain.models import LLMRequest, LLMResponse

FakeResponseItem = str | LLMResponse | Exception
FakeLLMHandler = Callable[
    [LLMRequest],
    str | LLMResponse | Awaitable[str | LLMResponse],
]

_DEFAULT_JSON_RESPONSE = (
    '{"action": "search", "query": "Anker earbuds", '
    '"country": "EG", "store": "both", "language": "en"}'
)
_DEFAULT_TEXT_RESPONSE = "Verified top marketplace offers ranked deterministically."


class FakeLLMClient:
    """Deterministic offline LLMClient supporting scripted queues and handler callbacks."""

    def __init__(
        self,
        responses: Sequence[FakeResponseItem] | None = None,
        *,
        handler: FakeLLMHandler | None = None,
        provider: str = "fake",
        model: str = "fake/deterministic",
    ) -> None:
        self._queue: deque[FakeResponseItem] = deque(responses or ())
        self._handler = handler
        self._provider = provider
        self._model = model
        self.requests: list[LLMRequest] = []

    @property
    def call_count(self) -> int:
        """Return total number of complete() invocations recorded."""
        return len(self.requests)

    def _to_response(self, value: str | LLMResponse) -> LLMResponse:
        if isinstance(value, LLMResponse):
            return value
        return LLMResponse(
            content=value,
            provider=self._provider,
            model=self._model,
            input_tokens=16,
            output_tokens=max(1, len(value.split())),
            latency_ms=0.5,
            used_fallback_model=False,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Record request and return scripted response, handler result, or safe default."""
        self.requests.append(request)

        if self._queue:
            item = self._queue.popleft()
            if isinstance(item, Exception):
                raise item
            return self._to_response(item)

        if self._handler is not None:
            produced = self._handler(request)
            if inspect.isawaitable(produced):
                produced = await produced
            return self._to_response(produced)

        default_content = _DEFAULT_JSON_RESPONSE if request.json_mode else _DEFAULT_TEXT_RESPONSE
        return self._to_response(default_content)

    async def aclose(self) -> None:
        """No-op async close matching live LLM client lifecycle hooks."""
        return None
