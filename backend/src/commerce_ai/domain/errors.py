"""Domain and infrastructure boundary exception hierarchy."""


class DomainError(Exception):
    """Base exception for all pure marketplace domain errors."""


class OfferValidationError(DomainError, ValueError):
    """Raised when an offer violates price, currency, or regional store URL rules."""


class CatalogProviderError(DomainError):
    """Raised when an upstream catalog provider fails during offer retrieval."""

    def __init__(self, provider: str, retriable: bool, reason: str) -> None:
        self.provider = provider
        self.retriable = retriable
        self.reason = reason
        super().__init__(f"[{provider}] (retriable={retriable}): {reason}")


class CacheStoreError(DomainError):
    """Raised when a cache backend encounters a connection or serialization failure."""


class LLMProviderError(DomainError):
    """Raised when an upstream LLM provider call fails or returns invalid output."""

    def __init__(self, provider: str, retriable: bool, reason: str) -> None:
        self.provider = provider
        self.retriable = retriable
        self.reason = reason
        super().__init__(f"[{provider}] (retriable={retriable}): {reason}")


class SessionStoreError(DomainError):
    """Raised when a session persistence backend encounters an initialization or I/O failure."""
