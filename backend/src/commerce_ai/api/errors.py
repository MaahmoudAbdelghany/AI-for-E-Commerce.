"""Unified sanitized FastAPI exception handlers and ASGI internal error guard."""

import logging
import re
import uuid
from typing import Any
from urllib.parse import unquote, urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from commerce_ai.api.schemas import ErrorResponse
from commerce_ai.config.settings import AppSettings, redact_url_password
from commerce_ai.domain.errors import (
    CatalogProviderError,
    DomainError,
    LLMProviderError,
    OfferValidationError,
)

logger = logging.getLogger(__name__)

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$", re.ASCII)
_EMBEDDED_URL_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"'<>]+")
_KV_SECRET_RE = re.compile(
    r"\b(password|passwd|pwd|secret|token|api[_-]?key)\b(\s*[:=]\s*)([^\s,;'\"]+)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"\b(Bearer)\s+([^\s,;'\"]+)", re.IGNORECASE)
_API_KEY_PREFIX_RE = re.compile(
    r"\b(?:AIza[0-9A-Za-z_-]{10,}|sk-[0-9A-Za-z_-]{10,}|gsk_[0-9A-Za-z_-]{10,})\b"
)


def _settings_secrets(settings: AppSettings | None) -> tuple[str, ...]:
    """Collect non-empty secret strings from AppSettings for defensive scrubbing."""
    if settings is None:
        return ()
    secrets: list[str] = []
    for attr in ("serper_api_key", "gemini_api_key", "groq_api_key", "openai_api_key"):
        secret_obj = getattr(settings, attr, None)
        if secret_obj is not None:
            raw = secret_obj.get_secret_value()
            if raw:
                secrets.append(raw)
    for url_attr in ("redis_url", "database_url"):
        raw_url = getattr(settings, url_attr, None)
        if isinstance(raw_url, str) and raw_url:
            try:
                parsed = urlsplit(raw_url)
                if parsed.password:
                    secrets.append(parsed.password)
                    decoded = unquote(parsed.password)
                    if decoded:
                        secrets.append(decoded)
            except ValueError:
                pass
    return tuple(secrets)


def scrub_error_text(text: str, *, settings: AppSettings | None = None) -> str:
    """Redact URLs, passwords, API keys, and stack-trace markers from diagnostic text."""
    if not text:
        return ""

    def _mask_url(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        return redact_url_password(raw_url) or "***"

    sanitized = text
    for url_attr in ("redis_url", "database_url"):
        raw_url = getattr(settings, url_attr, None) if settings is not None else None
        if isinstance(raw_url, str) and raw_url:
            redacted = redact_url_password(raw_url)
            if redacted:
                sanitized = sanitized.replace(raw_url, redacted)

    sanitized = _EMBEDDED_URL_RE.sub(_mask_url, sanitized)
    sanitized = _KV_SECRET_RE.sub(r"\1\2***", sanitized)
    sanitized = _BEARER_RE.sub(r"\1 ***", sanitized)
    sanitized = _API_KEY_PREFIX_RE.sub("***", sanitized)

    for secret in _settings_secrets(settings):
        sanitized = sanitized.replace(secret, "***")

    if "Traceback (most recent call last):" in sanitized:
        sanitized = sanitized.split("Traceback (most recent call last):", 1)[0].strip()

    return sanitized.strip()


def _settings_from_request(request: Request) -> AppSettings | None:
    raw = getattr(request.app.state, "settings", None)
    return raw if isinstance(raw, AppSettings) else None


def _resolve_request_id(request: Request) -> str:
    state_id = getattr(request.state, "request_id", None)
    if isinstance(state_id, str) and state_id:
        return state_id
    header_id = request.headers.get("x-request-id")
    if header_id is not None and _REQUEST_ID_RE.fullmatch(header_id) is not None:
        request.state.request_id = header_id
        return header_id
    generated = str(uuid.uuid4())
    request.state.request_id = generated
    return generated


def _error_json_response(
    request: Request,
    *,
    status_code: int,
    error_code: str,
    message: str,
    retriable: bool,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    request_id = _resolve_request_id(request)
    envelope = ErrorResponse(
        error_code=error_code,
        message=message,
        retriable=retriable,
        request_id=request_id,
        details=details,
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers={"X-Request-ID": request_id},
    )


async def handle_request_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 422 ErrorResponse with sanitized field-level validation details."""
    settings = _settings_from_request(request)
    details: list[dict[str, Any]] | None = None
    if isinstance(exc, RequestValidationError):
        details = [
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "msg": scrub_error_text(str(err.get("msg", "Invalid value")), settings=settings),
                "type": str(err.get("type", "value_error")),
            }
            for err in exc.errors()
        ]
    return _error_json_response(
        request,
        status_code=422,
        error_code="validation_error",
        message="Request validation failed.",
        retriable=False,
        details=details,
    )


async def handle_offer_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 422 ErrorResponse when domain offer/price validation fails."""
    settings = _settings_from_request(request)
    safe_message = scrub_error_text(str(exc), settings=settings) or "Offer validation failed."
    return _error_json_response(
        request,
        status_code=422,
        error_code="offer_validation_error",
        message=safe_message,
        retriable=False,
    )


async def handle_catalog_provider_error(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 503 ErrorResponse with retriability preserved from CatalogProviderError."""
    settings = _settings_from_request(request)
    retriable = exc.retriable if isinstance(exc, CatalogProviderError) else False
    raw_reason = exc.reason if isinstance(exc, CatalogProviderError) and exc.reason else str(exc)
    safe_message = (
        scrub_error_text(raw_reason, settings=settings)
        or "Catalog service is currently unavailable."
    )
    return _error_json_response(
        request,
        status_code=503,
        error_code="catalog_unavailable",
        message=safe_message,
        retriable=retriable,
    )


async def handle_llm_provider_error(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 503 ErrorResponse if an LLMProviderError reaches the HTTP boundary."""
    settings = _settings_from_request(request)
    retriable = exc.retriable if isinstance(exc, LLMProviderError) else False
    raw_reason = exc.reason if isinstance(exc, LLMProviderError) and exc.reason else str(exc)
    safe_message = (
        scrub_error_text(raw_reason, settings=settings) or "LLM service is currently unavailable."
    )
    return _error_json_response(
        request,
        status_code=503,
        error_code="llm_unavailable",
        message=safe_message,
        retriable=retriable,
    )


async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 400 ErrorResponse for uncaught domain rule errors."""
    settings = _settings_from_request(request)
    safe_message = scrub_error_text(str(exc), settings=settings) or "Domain validation error."
    return _error_json_response(
        request,
        status_code=400,
        error_code="domain_error",
        message=safe_message,
        retriable=False,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Log redacted failure details and emit a static safe HTTP 500 ErrorResponse."""
    settings = _settings_from_request(request)
    request_id = _resolve_request_id(request)
    safe_reason = scrub_error_text(str(exc), settings=settings)
    logger.error(
        "Unhandled %s on %s %s [request_id=%s]: %s",
        type(exc).__name__,
        request.method,
        request.url.path,
        request_id,
        safe_reason,
    )
    return _error_json_response(
        request,
        status_code=500,
        error_code="internal_error",
        message="An unexpected internal error occurred.",
        retriable=False,
    )


class UnhandledExceptionMiddleware:
    """ASGI guard inside CORS/RequestID layers converting unhandled exceptions to 500 JSON."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def _send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _send_wrapper)
        except Exception as exc:
            if response_started:
                raise
            response = await handle_unexpected_error(Request(scope), exc)
            await response(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    """Register unified ErrorResponse handlers on the FastAPI application."""
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(OfferValidationError, handle_offer_validation_error)
    app.add_exception_handler(CatalogProviderError, handle_catalog_provider_error)
    app.add_exception_handler(LLMProviderError, handle_llm_provider_error)
    app.add_exception_handler(DomainError, handle_domain_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
