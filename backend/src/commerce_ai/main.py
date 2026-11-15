"""FastAPI application factory, resilient async lifespan, and ASGI entrypoint."""

import inspect
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

from commerce_ai.adapters.cache.factory import create_cache_store
from commerce_ai.adapters.cache.memory import InMemoryTTLCache
from commerce_ai.adapters.cache.redis_store import RedisCacheStore
from commerce_ai.adapters.catalog.factory import create_catalog_provider
from commerce_ai.adapters.llm.factory import create_llm_client
from commerce_ai.adapters.session.factory import create_session_repository
from commerce_ai.adapters.session.memory import InMemorySessionStore
from commerce_ai.adapters.session.sqlalchemy_repo import SQLAlchemySessionRepository
from commerce_ai.agent.graph import ShoppingAssistantWorkflow
from commerce_ai.api.errors import register_exception_handlers, scrub_error_text
from commerce_ai.api.middleware import configure_middleware
from commerce_ai.api.routes import router as api_router
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.errors import SessionStoreError
from commerce_ai.domain.ports import CacheStore, CatalogProvider, LLMClient, SessionRepository

logger = logging.getLogger(__name__)

_APP_VERSION = "0.1.0"
_OPENAPI_TAGS: list[dict[str, Any]] = [
    {"name": "chat", "description": "Multi-turn Arabic/English shopping assistant workflow."},
    {"name": "search", "description": "Direct zero-LLM deterministic Top-3 catalog search."},
    {"name": "markets", "description": "Supported regional markets, currencies, and stores."},
    {"name": "system", "description": "Operational health and readiness probes."},
]


def _describe_session_repository(
    repo: SessionRepository,
    settings: AppSettings,
) -> tuple[str, bool]:
    """Return non-sensitive session backend label and degradation status."""
    if hasattr(repo, "backend_name") and hasattr(repo, "is_degraded"):
        return str(repo.backend_name), bool(repo.is_degraded)
    if isinstance(repo, SQLAlchemySessionRepository):
        lowered = settings.database_url.strip().lower()
        backend = "postgresql" if lowered.startswith("postgresql+") else "sqlite"
        return backend, False
    if isinstance(repo, InMemorySessionStore):
        return "memory", False
    return "custom", False


async def _safe_close_resource(resource: object | None, *, settings: AppSettings) -> None:
    """Close or dispose an owned async/sync adapter safely without leaking credentials."""
    if resource is None:
        return
    closer = getattr(resource, "aclose", None)
    if not callable(closer):
        closer = getattr(resource, "close", None)
    if not callable(closer):
        return
    try:
        result = closer()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        safe_reason = scrub_error_text(str(exc), settings=settings)
        logger.warning(
            "Error closing %s during shutdown: %s",
            type(resource).__name__,
            safe_reason,
        )


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Upgrade async cache, initialize session storage with fallback, and close owned adapters."""
    settings: AppSettings = application.state.settings
    shared_http_client: httpx.AsyncClient | None = (
        httpx.AsyncClient()
        if (application.state._owns_catalog_provider or application.state._owns_llm_client)
        else None
    )

    try:
        if application.state._owns_cache_store and application.state._owns_catalog_provider:
            previous_catalog = application.state.catalog_provider
            previous_cache = application.state.cache_store
            upgraded_cache = await create_cache_store(settings)
            application.state.cache_store = upgraded_cache
            if isinstance(upgraded_cache, RedisCacheStore):
                application.state.cache_backend = "redis"
                application.state.cache_degraded = False
            else:
                application.state.cache_backend = "memory"
                application.state.cache_degraded = bool(settings.redis_url)
            application.state.catalog_provider = create_catalog_provider(
                settings,
                cache=upgraded_cache,
                http_client=shared_http_client,
            )
            await _safe_close_resource(previous_catalog, settings=settings)
            await _safe_close_resource(previous_cache, settings=settings)

        if application.state._owns_llm_client:
            previous_llm = application.state.llm_client
            application.state.llm_client = create_llm_client(
                settings,
                http_client=shared_http_client,
            )
            await _safe_close_resource(previous_llm, settings=settings)

        repo: SessionRepository = application.state.session_repository
        init_fn = getattr(repo, "initialize", None)
        if callable(init_fn):
            try:
                init_result = init_fn()
                if inspect.isawaitable(init_result):
                    await init_result
            except (SessionStoreError, OSError, TimeoutError, ValueError, RuntimeError) as exc:
                safe_reason = scrub_error_text(str(exc), settings=settings)
                logger.warning(
                    "Session storage initialization failed; falling back to memory: %s",
                    safe_reason,
                )
                if application.state._owns_session_repository:
                    await _safe_close_resource(repo, settings=settings)
                fallback_repo = InMemorySessionStore(max_turns=settings.session_max_turns)
                await fallback_repo.initialize()
                application.state.session_repository = fallback_repo
                application.state._owns_session_repository = True
                application.state.session_backend = "memory"
                application.state.session_degraded = True
            else:
                backend_name, is_degraded = _describe_session_repository(repo, settings)
                application.state.session_backend = backend_name
                application.state.session_degraded = is_degraded

        if application.state._owns_workflow:
            application.state.workflow = ShoppingAssistantWorkflow(
                settings=settings,
                catalog_provider=application.state.catalog_provider,
                session_repository=application.state.session_repository,
                llm_client=application.state.llm_client,
                scoring_config=settings.scoring,
            )

        yield
    finally:
        if application.state._owns_catalog_provider:
            await _safe_close_resource(application.state.catalog_provider, settings=settings)
        if application.state._owns_cache_store:
            await _safe_close_resource(application.state.cache_store, settings=settings)
        if application.state._owns_llm_client:
            await _safe_close_resource(application.state.llm_client, settings=settings)
        if shared_http_client is not None:
            await _safe_close_resource(shared_http_client, settings=settings)
        if application.state._owns_session_repository:
            await _safe_close_resource(application.state.session_repository, settings=settings)


def create_app(
    settings: AppSettings | None = None,
    *,
    catalog_provider: CatalogProvider | None = None,
    llm_client: LLMClient | None = None,
    session_repository: SessionRepository | None = None,
    workflow: ShoppingAssistantWorkflow | None = None,
) -> FastAPI:
    """Create and configure the versioned FastAPI service with optional injected adapters."""
    resolved_settings = settings if settings is not None else AppSettings()

    owns_cache_store = catalog_provider is None
    owns_catalog_provider = catalog_provider is None
    owns_llm_client = llm_client is None and workflow is None
    owns_session_repository = session_repository is None
    owns_workflow = workflow is None

    resolved_cache_store: CacheStore | None
    resolved_catalog_provider: CatalogProvider
    if catalog_provider is not None:
        resolved_cache_store = None
        resolved_catalog_provider = catalog_provider
        cache_backend = "custom"
    else:
        resolved_cache_store = InMemoryTTLCache()
        resolved_catalog_provider = create_catalog_provider(
            resolved_settings,
            cache=resolved_cache_store,
        )
        cache_backend = "memory"

    resolved_llm_client: LLMClient | None
    if llm_client is not None:
        resolved_llm_client = llm_client
    elif workflow is not None:
        resolved_llm_client = None
    else:
        resolved_llm_client = create_llm_client(resolved_settings)

    resolved_session_repo = (
        session_repository
        if session_repository is not None
        else create_session_repository(resolved_settings)
    )
    session_backend, session_degraded = _describe_session_repository(
        resolved_session_repo,
        resolved_settings,
    )

    resolved_workflow = (
        workflow
        if workflow is not None
        else ShoppingAssistantWorkflow(
            settings=resolved_settings,
            catalog_provider=resolved_catalog_provider,
            session_repository=resolved_session_repo,
            llm_client=resolved_llm_client,
            scoring_config=resolved_settings.scoring,
        )
    )

    application = FastAPI(
        title="AI for E-Commerce API",
        version=_APP_VERSION,
        description=(
            "Versioned REST API for regional Noon & Amazon shopping search, "
            "deterministic Top-3 value ranking, and bounded LangGraph conversations."
        ),
        openapi_tags=_OPENAPI_TAGS,
        lifespan=_lifespan,
    )

    application.state.settings = resolved_settings
    application.state.cache_store = resolved_cache_store
    application.state.cache_backend = cache_backend
    application.state.cache_degraded = False
    application.state.catalog_provider = resolved_catalog_provider
    application.state.llm_client = resolved_llm_client
    application.state.session_repository = resolved_session_repo
    application.state.session_backend = session_backend
    application.state.session_degraded = session_degraded
    application.state.workflow = resolved_workflow

    application.state._owns_cache_store = owns_cache_store
    application.state._owns_catalog_provider = owns_catalog_provider
    application.state._owns_llm_client = owns_llm_client
    application.state._owns_session_repository = owns_session_repository
    application.state._owns_workflow = owns_workflow

    register_exception_handlers(application)
    configure_middleware(application, resolved_settings)
    application.include_router(api_router)
    return application


app = create_app()
