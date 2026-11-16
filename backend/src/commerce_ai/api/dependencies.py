"""Typed FastAPI dependency accessors reading pre-wired application and request state."""

import uuid
from typing import cast

from fastapi import Request

from commerce_ai.agent.graph import ShoppingAssistantWorkflow
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.ports import CatalogProvider


def get_settings(request: Request) -> AppSettings:
    """Return the AppSettings instance attached to app.state."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise RuntimeError("Application settings are not initialized on app.state")
    return cast(AppSettings, settings)


def get_workflow(request: Request) -> ShoppingAssistantWorkflow:
    """Return the ShoppingAssistantWorkflow attached to app.state."""
    workflow = getattr(request.app.state, "workflow", None)
    if workflow is None:
        raise RuntimeError("ShoppingAssistantWorkflow is not initialized on app.state")
    return cast(ShoppingAssistantWorkflow, workflow)


def get_catalog_provider(request: Request) -> CatalogProvider:
    """Return the CatalogProvider attached to app.state."""
    provider = getattr(request.app.state, "catalog_provider", None)
    if provider is None:
        raise RuntimeError("CatalogProvider is not initialized on app.state")
    return cast(CatalogProvider, provider)


def get_request_id(request: Request) -> str:
    """Return the validated request ID bound on request.state or generate a fallback UUID4."""
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    generated = str(uuid.uuid4())
    request.state.request_id = generated
    return generated
