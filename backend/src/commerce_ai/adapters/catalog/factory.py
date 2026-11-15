"""Honest catalog provider factory honoring AppSettings.catalog_mode without silent fallback."""

import httpx

from commerce_ai.adapters.catalog.cached_provider import CachedCatalogProvider
from commerce_ai.adapters.catalog.seed_provider import SeedCatalogProvider
from commerce_ai.adapters.catalog.serper_provider import SerperShoppingProvider
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.errors import CatalogProviderError
from commerce_ai.domain.ports import CacheStore, CatalogProvider


def create_catalog_provider(
    settings: AppSettings,
    *,
    cache: CacheStore | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> CatalogProvider:
    """Resolve SeedCatalogProvider or SerperShoppingProvider and optionally wrap with cache."""
    api_key = settings.serper_api_key
    has_api_key = api_key is not None and bool(api_key.get_secret_value().strip())

    provider: CatalogProvider
    if settings.catalog_mode == "seed":
        provider = SeedCatalogProvider()
    elif settings.catalog_mode == "serper":
        if not has_api_key or api_key is None:
            raise CatalogProviderError(
                provider="serper",
                retriable=False,
                reason="SERPER_API_KEY is required when catalog_mode is 'serper'",
            )
        provider = SerperShoppingProvider(
            api_key=api_key,
            timeout_seconds=settings.serper_timeout_seconds,
            client=http_client,
        )
    elif settings.catalog_mode == "auto":
        if has_api_key and api_key is not None:
            provider = SerperShoppingProvider(
                api_key=api_key,
                timeout_seconds=settings.serper_timeout_seconds,
                client=http_client,
            )
        else:
            provider = SeedCatalogProvider()
    else:
        raise CatalogProviderError(
            provider="catalog",
            retriable=False,
            reason=f"Unsupported catalog_mode: {settings.catalog_mode!r}",
        )

    if cache is not None:
        return CachedCatalogProvider(
            provider=provider,
            cache=cache,
            ttl_seconds=settings.cache_ttl_seconds,
        )
    return provider
