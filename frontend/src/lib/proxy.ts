import { NextRequest, NextResponse } from "next/server";

import type { ErrorResponse } from "@/lib/contracts";

const DEFAULT_BACKEND_API_URL = "http://127.0.0.1:8000";
const REQUEST_ID_RE = /^[A-Za-z0-9._:-]{1,128}$/;
const V1_TIMEOUT_MS = 12_000;
const HEALTH_TIMEOUT_MS = 5_000;

interface AllowedRouteSpec {
  method: "GET" | "POST";
  upstreamPath: string;
}

const ALLOWED_V1_ROUTES: Record<string, AllowedRouteSpec> = {
  markets: { method: "GET", upstreamPath: "/api/v1/markets" },
  chat: { method: "POST", upstreamPath: "/api/v1/chat" },
  search: { method: "POST", upstreamPath: "/api/v1/search" },
};

export function resolveBackendApiUrl(): string {
  const raw = process.env.BACKEND_API_URL;
  const candidate = raw && raw.trim().length > 0 ? raw.trim() : DEFAULT_BACKEND_API_URL;
  return candidate.replace(/\/+$/, "");
}

function resolveRequestId(request: NextRequest): string {
  const incoming = request.headers.get("x-request-id")?.trim();
  if (incoming && REQUEST_ID_RE.test(incoming)) {
    return incoming;
  }
  return crypto.randomUUID();
}

function jsonErrorResponse(
  status: number,
  error: ErrorResponse,
  extraHeaders?: Record<string, string>,
): NextResponse {
  return NextResponse.json(error, {
    status,
    headers: {
      "X-Request-ID": error.request_id,
      "Cache-Control": "no-store",
      ...(extraHeaders ?? {}),
    },
  });
}

function sanitizeHeaderValue(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const cleaned = value.replace(/[\r\n\u0000-\u001F\u007F]/g, "").trim();
  return cleaned.length > 0 ? cleaned : null;
}

function hasPathTraversalOrBadEncoding(request: NextRequest, segments: string[]): boolean {
  const pathname = request.nextUrl?.pathname ?? "";
  const lowerPath = pathname.toLowerCase();
  if (
    lowerPath.includes("%2e") ||
    lowerPath.includes("%2f") ||
    lowerPath.includes("%5c") ||
    pathname.includes("\\") ||
    pathname.includes("..")
  ) {
    return true;
  }

  for (const segment of segments) {
    const trimmed = segment.trim();
    if (!trimmed || trimmed === "." || trimmed === ".." || trimmed.includes("\\")) {
      return true;
    }
    const lowerSeg = trimmed.toLowerCase();
    if (lowerSeg.includes("%2e") || lowerSeg.includes("%2f") || lowerSeg.includes("%5c")) {
      return true;
    }
  }
  return false;
}

async function forwardToBackend(
  request: NextRequest,
  upstreamPath: string,
  timeoutMs: number,
  requestId: string,
): Promise<NextResponse> {
  const backendBase = resolveBackendApiUrl();
  let targetUrl: string;
  try {
    const parsed = new URL(upstreamPath, `${backendBase}/`);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw new Error("Invalid upstream protocol");
    }
    targetUrl = parsed.toString();
  } catch {
    return jsonErrorResponse(503, {
      error_code: "backend_unreachable",
      message: "Backend service is temporarily unavailable.",
      retriable: true,
      request_id: requestId,
      details: null,
    });
  }

  const forwardHeaders = new Headers();
  forwardHeaders.set("Accept", sanitizeHeaderValue(request.headers.get("accept")) ?? "application/json");
  forwardHeaders.set("X-Request-ID", requestId);

  const forwardedFor = sanitizeHeaderValue(request.headers.get("x-forwarded-for"));
  if (forwardedFor) {
    forwardHeaders.set("X-Forwarded-For", forwardedFor);
  }

  const method = request.method.toUpperCase();
  let body: string | undefined;
  if (method === "POST") {
    forwardHeaders.set(
      "Content-Type",
      sanitizeHeaderValue(request.headers.get("content-type")) ?? "application/json",
    );
    body = await request.text();
  }

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(targetUrl, {
      method,
      headers: forwardHeaders,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    return jsonErrorResponse(503, {
      error_code: "backend_unreachable",
      message: "Backend service is temporarily unavailable.",
      retriable: true,
      request_id: requestId,
      details: null,
    });
  }

  const responseText = await upstreamResponse.text();
  const responseHeaders = new Headers();
  responseHeaders.set(
    "Content-Type",
    upstreamResponse.headers.get("content-type") ?? "application/json",
  );
  responseHeaders.set(
    "X-Request-ID",
    sanitizeHeaderValue(upstreamResponse.headers.get("x-request-id")) ?? requestId,
  );
  responseHeaders.set("Cache-Control", "no-store");

  const retryAfter = sanitizeHeaderValue(upstreamResponse.headers.get("retry-after"));
  if (retryAfter) {
    responseHeaders.set("Retry-After", retryAfter);
  }

  return new NextResponse(responseText, {
    status: upstreamResponse.status,
    headers: responseHeaders,
  });
}

export async function proxyV1Request(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
): Promise<NextResponse> {
  const requestId = resolveRequestId(request);
  const resolvedParams = await context.params;
  const segments = resolvedParams.path ?? [];

  if (hasPathTraversalOrBadEncoding(request, segments) || segments.length !== 1) {
    return jsonErrorResponse(404, {
      error_code: "route_not_found",
      message: "Requested API route was not found.",
      retriable: false,
      request_id: requestId,
      details: null,
    });
  }

  const segment = segments[0] ?? "";
  const routeSpec = Object.prototype.hasOwnProperty.call(ALLOWED_V1_ROUTES, segment)
    ? ALLOWED_V1_ROUTES[segment]
    : undefined;

  if (!routeSpec) {
    return jsonErrorResponse(404, {
      error_code: "route_not_found",
      message: "Requested API route was not found.",
      retriable: false,
      request_id: requestId,
      details: null,
    });
  }

  const method = request.method.toUpperCase();
  if (method !== routeSpec.method) {
    return jsonErrorResponse(
      405,
      {
        error_code: "method_not_allowed",
        message: `Method ${method} is not allowed on this route.`,
        retriable: false,
        request_id: requestId,
        details: null,
      },
      { Allow: routeSpec.method },
    );
  }

  return forwardToBackend(request, routeSpec.upstreamPath, V1_TIMEOUT_MS, requestId);
}

export async function proxyHealthRequest(request: NextRequest): Promise<NextResponse> {
  const requestId = resolveRequestId(request);
  const method = request.method.toUpperCase();
  if (method !== "GET") {
    return jsonErrorResponse(
      405,
      {
        error_code: "method_not_allowed",
        message: `Method ${method} is not allowed on this route.`,
        retriable: false,
        request_id: requestId,
        details: null,
      },
      { Allow: "GET" },
    );
  }

  return forwardToBackend(request, "/health", HEALTH_TIMEOUT_MS, requestId);
}
