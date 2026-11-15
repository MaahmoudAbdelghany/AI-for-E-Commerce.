"""ASGI middleware for X-Request-ID tracing, CORS, and sliding-window rate limiting."""

import asyncio
import ipaddress
import math
import re
import time
import uuid
from collections import OrderedDict, deque
from collections.abc import Callable, Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from commerce_ai.api.errors import UnhandledExceptionMiddleware
from commerce_ai.api.schemas import ErrorResponse
from commerce_ai.config.settings import AppSettings

VALID_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$", re.ASCII)
DEFAULT_RATE_LIMITED_PATHS: frozenset[str] = frozenset({"/api/v1/chat", "/api/v1/search"})

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def parse_trusted_proxy_networks(cidrs: Sequence[str]) -> tuple[IPNetwork, ...]:
    """Parse CIDR strings into immutable IPv4/IPv6 network objects."""
    return tuple(ipaddress.ip_network(cidr, strict=False) for cidr in cidrs)


def _parse_ip(raw: str) -> IPAddress | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return ipaddress.ip_address(cleaned)
    except ValueError:
        return None


def _is_trusted_ip(addr: IPAddress, trusted_networks: tuple[IPNetwork, ...]) -> bool:
    return any(addr in net for net in trusted_networks)


def extract_client_ip(
    scope: Scope,
    *,
    trusted_proxies: Sequence[IPNetwork] | Sequence[str] = (),
) -> str:
    """Extract client IP, trusting X-Forwarded-For right-to-left only from trusted proxies."""
    client = scope.get("client")
    peer_host: str | None = None
    if isinstance(client, (tuple, list)) and client:
        raw_host = client[0]
        if isinstance(raw_host, str) and raw_host.strip():
            peer_host = raw_host.strip()

    if peer_host is None:
        return "unknown"

    peer_ip = _parse_ip(peer_host)
    if peer_ip is None:
        return peer_host

    if not trusted_proxies:
        return str(peer_ip)

    trusted_networks = tuple(
        net
        if isinstance(net, (ipaddress.IPv4Network, ipaddress.IPv6Network))
        else ipaddress.ip_network(net, strict=False)
        for net in trusted_proxies
    )
    if not _is_trusted_ip(peer_ip, trusted_networks):
        return str(peer_ip)

    headers = Headers(scope=scope)
    forwarded_for = headers.get("x-forwarded-for")
    if forwarded_for:
        hops = [part.strip() for part in forwarded_for.split(",") if part.strip()]
        for hop in reversed(hops):
            hop_ip = _parse_ip(hop)
            if hop_ip is None:
                break
            if not _is_trusted_ip(hop_ip, trusted_networks):
                return str(hop_ip)

    return str(peer_ip)


class RequestIDMiddleware:
    """ASGI middleware validating or generating X-Request-ID and propagating it to responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_header = Headers(scope=scope).get("x-request-id")
        if raw_header is not None and VALID_REQUEST_ID_RE.fullmatch(raw_header) is not None:
            request_id = raw_header
        else:
            request_id = str(uuid.uuid4())

        state = scope.get("state")
        if isinstance(state, dict):
            state["request_id"] = request_id
        else:
            scope["state"] = {"request_id": request_id}

        async def _send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        await self.app(scope, receive, _send_wrapper)


class SlidingWindowRateLimiter:
    """Coroutine-safe bounded-LRU sliding-window per-client rate limiter."""

    def __init__(
        self,
        *,
        limit_rpm: int,
        window_seconds: float = 60.0,
        max_clients: int = 10_000,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if limit_rpm < 0:
            raise ValueError("limit_rpm must be >= 0")
        if window_seconds <= 0.0:
            raise ValueError("window_seconds must be positive")
        if max_clients <= 0:
            raise ValueError("max_clients must be positive")

        self._limit_rpm = limit_rpm
        self._window_seconds = window_seconds
        self._max_clients = max_clients
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._lock = asyncio.Lock()
        self._buckets: OrderedDict[str, deque[float]] = OrderedDict()

    @property
    def limit_rpm(self) -> int:
        """Return configured requests-per-minute limit (0 disables limiting)."""
        return self._limit_rpm

    @property
    def window_seconds(self) -> float:
        """Return sliding window duration in seconds."""
        return self._window_seconds

    def _prune_stale_locked(self, cutoff: float) -> None:
        stale_keys = [
            key
            for key, timestamps in self._buckets.items()
            if not timestamps or timestamps[-1] <= cutoff
        ]
        for key in stale_keys:
            del self._buckets[key]

    async def check(self, client_key: str) -> tuple[bool, int]:
        """Record request if under limit; return (allowed, retry_after_seconds)."""
        if self._limit_rpm <= 0:
            return True, 0

        async with self._lock:
            now = self._clock()
            cutoff = now - self._window_seconds
            bucket = self._buckets.get(client_key)

            if bucket is None:
                if len(self._buckets) >= self._max_clients:
                    self._prune_stale_locked(cutoff)
                    while len(self._buckets) >= self._max_clients:
                        self._buckets.popitem(last=False)
                bucket = deque()
                self._buckets[client_key] = bucket
            else:
                self._buckets.move_to_end(client_key)
                while bucket and bucket[0] <= cutoff:
                    bucket.popleft()

            if len(bucket) >= self._limit_rpm:
                oldest = bucket[0]
                remaining = max(0.0, (oldest + self._window_seconds) - now)
                max_retry = max(1, int(math.ceil(self._window_seconds)))
                retry_after = max(1, min(max_retry, math.ceil(remaining)))
                return False, retry_after

            bucket.append(now)
            return True, 0


class SlidingWindowRateLimitMiddleware:
    """ASGI middleware enforcing per-client sliding-window limits on search and chat routes."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        rate_limit_rpm: int = 60,
        window_seconds: float = 60.0,
        max_clients: int = 10_000,
        clock: Callable[[], float] | None = None,
        protected_paths: frozenset[str] = DEFAULT_RATE_LIMITED_PATHS,
        trusted_proxy_cidrs: Sequence[str] = ("127.0.0.1/32", "::1/128"),
    ) -> None:
        self.app = app
        self._protected_paths = protected_paths
        self._trusted_proxies = parse_trusted_proxy_networks(trusted_proxy_cidrs)
        self._limiter = SlidingWindowRateLimiter(
            limit_rpm=rate_limit_rpm,
            window_seconds=window_seconds,
            max_clients=max_clients,
            clock=clock,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._limiter.limit_rpm <= 0:
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        raw_path = str(scope.get("path", "/"))
        normalized_path = raw_path.rstrip("/") or "/"
        if normalized_path not in self._protected_paths:
            await self.app(scope, receive, send)
            return

        client_key = extract_client_ip(scope, trusted_proxies=self._trusted_proxies)
        allowed, retry_after = await self._limiter.check(client_key)
        if allowed:
            await self.app(scope, receive, send)
            return

        state = scope.get("state")
        state_id = state.get("request_id") if isinstance(state, dict) else None
        request_id = state_id if isinstance(state_id, str) and state_id else str(uuid.uuid4())
        envelope = ErrorResponse(
            error_code="rate_limit_exceeded",
            message="Rate limit exceeded. Please retry later.",
            retriable=True,
            request_id=request_id,
            details=None,
        )
        response = JSONResponse(
            status_code=429,
            content=envelope.model_dump(mode="json"),
            headers={"Retry-After": str(retry_after), "X-Request-ID": request_id},
        )
        await response(scope, receive, send)


def configure_middleware(
    app: FastAPI,
    settings: AppSettings,
    *,
    clock: Callable[[], float] | None = None,
) -> None:
    """Register RequestID -> CORS -> RateLimiter -> UnhandledException stack (LIFO)."""
    app.add_middleware(UnhandledExceptionMiddleware)
    app.add_middleware(
        SlidingWindowRateLimitMiddleware,
        rate_limit_rpm=settings.rate_limit_rpm,
        clock=clock,
        trusted_proxy_cidrs=settings.trusted_proxy_cidrs,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID", "Accept"],
        allow_credentials=False,
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestIDMiddleware)
