import { isIP } from "node:net";
import { NextRequest, NextResponse } from "next/server";

import type { ErrorResponse } from "@/lib/contracts";

const DEFAULT_BACKEND_API_URL = "http://127.0.0.1:8000";
const REQUEST_ID_RE = /^[A-Za-z0-9._:-]{1,128}$/;
const DEFAULT_V1_TIMEOUT_MS = 12_000;
const MIN_PROXY_TIMEOUT_MS = 1_000;
const MAX_PROXY_TIMEOUT_MS = 60_000;
const HEALTH_TIMEOUT_MS = 5_000;
const MAX_POST_BODY_BYTES = 65_536;

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

export function resolveV1TimeoutMs(): number {
  const raw = process.env.BACKEND_PROXY_TIMEOUT_MS?.trim();
  if (!raw) {
    return DEFAULT_V1_TIMEOUT_MS;
  }
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_V1_TIMEOUT_MS;
  }
  return Math.min(MAX_PROXY_TIMEOUT_MS, Math.max(MIN_PROXY_TIMEOUT_MS, Math.trunc(parsed)));
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
  return new NextResponse(JSON.stringify(error), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "X-Content-Type-Options": "nosniff",
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

function sanitizeTrustedForwardedFor(request: NextRequest): string | null {
  if (process.env.TRUST_PROXY_HEADERS !== "true") {
    return null;
  }
  const cleaned = sanitizeHeaderValue(request.headers.get("x-forwarded-for"));
  if (!cleaned) {
    return null;
  }
  const hops = cleaned
    .split(",")
    .map((hop) => hop.trim())
    .filter((hop) => hop.length > 0);
  if (hops.length === 0 || !hops.every((hop) => isIP(hop) !== 0)) {
    return null;
  }
  return hops.join(", ");
}

function isJsonContentType(rawContentType: string | null): boolean {
  if (!rawContentType) {
    return false;
  }
  const mediaType = rawContentType.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  return mediaType === "application/json" || (mediaType.includes("/") && mediaType.endsWith("+json"));
}

function createUpstreamAbortSignal(
  timeoutMs: number,
  requestSignal?: AbortSignal,
): { signal: AbortSignal; cleanup: () => void } {
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  if (!requestSignal) {
    return { signal: timeoutSignal, cleanup: () => {} };
  }
  if (typeof AbortSignal.any === "function") {
    try {
      return { signal: AbortSignal.any([timeoutSignal, requestSignal]), cleanup: () => {} };
    } catch {
      // Fallback below if cross-realm AbortSignal instances cannot be combined via AbortSignal.any.
    }
  }
  const controller = new AbortController();
  if (requestSignal.aborted) {
    controller.abort(requestSignal.reason);
    return { signal: controller.signal, cleanup: () => {} };
  }
  if (timeoutSignal.aborted) {
    controller.abort(timeoutSignal.reason);
    return { signal: controller.signal, cleanup: () => {} };
  }
  const onRequestAbort = () => controller.abort(requestSignal.reason);
  const onTimeoutAbort = () => controller.abort(timeoutSignal.reason);
  requestSignal.addEventListener("abort", onRequestAbort, { once: true });
  timeoutSignal.addEventListener("abort", onTimeoutAbort, { once: true });
  return {
    signal: controller.signal,
    cleanup: () => {
      requestSignal.removeEventListener("abort", onRequestAbort);
      timeoutSignal.removeEventListener("abort", onTimeoutAbort);
    },
  };
}

async function readBoundedPostBody(
  request: NextRequest,
): Promise<{ ok: true; body: string } | { ok: false }> {
  const rawLength = request.headers.get("content-length")?.trim();
  if (rawLength && /^\d+$/.test(rawLength)) {
    const declaredBytes = Number(rawLength);
    if (Number.isFinite(declaredBytes) && declaredBytes > MAX_POST_BODY_BYTES) {
      return { ok: false };
    }
  }

  if (request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let totalBytes = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        if (value) {
          totalBytes += value.byteLength;
          if (totalBytes > MAX_POST_BODY_BYTES) {
            await reader.cancel().catch(() => {});
            return { ok: false };
          }
          chunks.push(value);
        }
      }
    } finally {
      reader.releaseLock();
    }

    const merged = new Uint8Array(totalBytes);
    let offset = 0;
    for (const chunk of chunks) {
      merged.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return { ok: true, body: new TextDecoder().decode(merged) };
  }

  const text = await request.text();
  if (Buffer.byteLength(text, "utf8") > MAX_POST_BODY_BYTES) {
    return { ok: false };
  }
  return { ok: true, body: text };
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

  const forwardedFor = sanitizeTrustedForwardedFor(request);
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
    const bounded = await readBoundedPostBody(request);
    if (!bounded.ok) {
      return jsonErrorResponse(413, {
        error_code: "payload_too_large",
        message: "Request body exceeds the maximum allowed size of 64 KiB.",
        retriable: false,
        request_id: requestId,
        details: null,
      });
    }
    body = bounded.body;
  }

  const { signal, cleanup } = createUpstreamAbortSignal(timeoutMs, request.signal);
  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(targetUrl, {
      method,
      headers: forwardHeaders,
      body,
      cache: "no-store",
      redirect: "error",
      signal,
    });
  } catch {
    return jsonErrorResponse(503, {
      error_code: "backend_unreachable",
      message: "Backend service is temporarily unavailable.",
      retriable: true,
      request_id: requestId,
      details: null,
    });
  } finally {
    cleanup();
  }

  const responseText = await upstreamResponse.text();
  const rawUpstreamRequestId = sanitizeHeaderValue(upstreamResponse.headers.get("x-request-id"));
  const effectiveRequestId =
    rawUpstreamRequestId && REQUEST_ID_RE.test(rawUpstreamRequestId)
      ? rawUpstreamRequestId
      : requestId;

  let isValidJson = false;
  if (isJsonContentType(upstreamResponse.headers.get("content-type"))) {
    try {
      JSON.parse(responseText);
      isValidJson = true;
    } catch {
      isValidJson = false;
    }
  }

  if (!isValidJson) {
    const isUpstreamServerError = upstreamResponse.status >= 500;
    return jsonErrorResponse(isUpstreamServerError ? upstreamResponse.status : 502, {
      error_code: isUpstreamServerError ? "backend_unreachable" : "upstream_invalid_response",
      message: isUpstreamServerError
        ? "Backend service is temporarily unavailable."
        : "Backend service returned an invalid response.",
      retriable: true,
      request_id: effectiveRequestId,
      details: null,
    });
  }

  const responseHeaders = new Headers();
  responseHeaders.set("Content-Type", "application/json; charset=utf-8");
  responseHeaders.set("X-Content-Type-Options", "nosniff");
  responseHeaders.set("X-Request-ID", effectiveRequestId);
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

  return forwardToBackend(request, routeSpec.upstreamPath, resolveV1TimeoutMs(), requestId);
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
