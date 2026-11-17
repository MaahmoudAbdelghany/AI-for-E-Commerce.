import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DELETE as healthDelete,
  dynamic as healthDynamic,
  GET as healthGet,
  PATCH as healthPatch,
  POST as healthPost,
  PUT as healthPut,
} from "@/app/api/health/route";
import {
  DELETE as v1Delete,
  dynamic as v1Dynamic,
  GET as v1Get,
  HEAD as v1Head,
  PATCH as v1Patch,
  POST as v1Post,
  PUT as v1Put,
} from "@/app/api/v1/[...path]/route";
import { resolveV1TimeoutMs } from "@/lib/proxy";

describe("runtime proxy Route Handlers (integration & security)", () => {
  const originalBackendUrl = process.env.BACKEND_API_URL;
  const originalTrustProxyHeaders = process.env.TRUST_PROXY_HEADERS;
  const originalProxyTimeoutMs = process.env.BACKEND_PROXY_TIMEOUT_MS;

  beforeEach(() => {
    delete process.env.TRUST_PROXY_HEADERS;
    delete process.env.BACKEND_PROXY_TIMEOUT_MS;
  });

  afterEach(() => {
    if (originalBackendUrl === undefined) {
      delete process.env.BACKEND_API_URL;
    } else {
      process.env.BACKEND_API_URL = originalBackendUrl;
    }
    if (originalTrustProxyHeaders === undefined) {
      delete process.env.TRUST_PROXY_HEADERS;
    } else {
      process.env.TRUST_PROXY_HEADERS = originalTrustProxyHeaders;
    }
    if (originalProxyTimeoutMs === undefined) {
      delete process.env.BACKEND_PROXY_TIMEOUT_MS;
    } else {
      process.env.BACKEND_PROXY_TIMEOUT_MS = originalProxyTimeoutMs;
    }
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("v1 proxy forwards allowlisted routes, body/headers/signal/redirect=error, and omits untrusted X-Forwarded-For by default", async () => {
    expect(v1Dynamic).toBe("force-dynamic");
    process.env.BACKEND_API_URL = "http://runtime-backend.internal:8080/";

    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            markets: [],
            default_country: "EG",
            default_store: "both",
            request_id: "up-mkt-1",
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "X-Request-ID": "up-mkt-1",
            },
          },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error_code: "rate_limit_exceeded",
            message: "Rate limit exceeded. Please retry later.",
            retriable: true,
            request_id: "up-chat-429",
            details: null,
          }),
          {
            status: 429,
            headers: {
              "Content-Type": "application/json",
              "X-Request-ID": "up-chat-429",
              "Retry-After": "30",
            },
          },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error_code: "validation_error",
            message: "Request validation failed.",
            retriable: false,
            request_id: "up-search-422",
            details: [{ loc: ["body", "query"], msg: "blank" }],
          }),
          {
            status: 422,
            headers: {
              "Content-Type": "application/problem+json; charset=utf-8",
              "X-Request-ID": "up-search-422",
            },
          },
        ),
      );

    vi.stubGlobal("fetch", fetchMock);

    const marketsRes = await v1Get(
      new NextRequest("http://localhost:3000/api/v1/markets", {
        method: "GET",
        headers: {
          Accept: "application/json",
          "X-Request-ID": "client-req-1",
          "X-Forwarded-For": "203.0.113.5",
        },
      }),
      { params: Promise.resolve({ path: ["markets"] }) },
    );

    expect(marketsRes.status).toBe(200);
    expect(marketsRes.headers.get("x-request-id")).toBe("up-mkt-1");
    expect(marketsRes.headers.get("content-type")).toBe("application/json; charset=utf-8");
    expect(marketsRes.headers.get("x-content-type-options")).toBe("nosniff");
    expect(await marketsRes.json()).toMatchObject({ request_id: "up-mkt-1" });

    const chatBody = JSON.stringify({ message: "سماعة أنكر" });
    const chatRes = await v1Post(
      new NextRequest("http://localhost:3000/api/v1/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": "client-req-2",
        },
        body: chatBody,
      }),
      { params: Promise.resolve({ path: ["chat"] }) },
    );

    expect(chatRes.status).toBe(429);
    expect(chatRes.headers.get("retry-after")).toBe("30");
    expect(chatRes.headers.get("x-request-id")).toBe("up-chat-429");
    expect(chatRes.headers.get("x-content-type-options")).toBe("nosniff");

    const searchBody = JSON.stringify({ query: "   " });
    const searchRes = await v1Post(
      new NextRequest("http://localhost:3000/api/v1/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: searchBody,
      }),
      { params: Promise.resolve({ path: ["search"] }) },
    );

    expect(searchRes.status).toBe(422);
    expect(searchRes.headers.get("content-type")).toBe("application/json; charset=utf-8");
    expect(searchRes.headers.get("x-content-type-options")).toBe("nosniff");
    expect(await searchRes.json()).toMatchObject({ error_code: "validation_error" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://runtime-backend.internal:8080/api/v1/markets",
      expect.objectContaining({
        method: "GET",
        cache: "no-store",
        redirect: "error",
        signal: expect.any(AbortSignal),
      }),
    );
    const firstHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(firstHeaders.get("accept")).toBe("application/json");
    expect(firstHeaders.get("x-request-id")).toBe("client-req-1");
    expect(firstHeaders.get("x-forwarded-for")).toBeNull();

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://runtime-backend.internal:8080/api/v1/chat",
      expect.objectContaining({
        method: "POST",
        body: chatBody,
        cache: "no-store",
        redirect: "error",
        signal: expect.any(AbortSignal),
      }),
    );
    const secondHeaders = fetchMock.mock.calls[1]?.[1]?.headers as Headers;
    expect(secondHeaders.get("content-type")).toBe("application/json");

    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://runtime-backend.internal:8080/api/v1/search",
      expect.objectContaining({
        method: "POST",
        body: searchBody,
        cache: "no-store",
        redirect: "error",
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it("health proxy forwards runtime /health, rejects POST/PUT/PATCH/DELETE with 405, and maps outage to sanitized 503", async () => {
    expect(healthDynamic).toBe("force-dynamic");
    process.env.BACKEND_API_URL = "http://secret-backend.internal:9123";

    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: "ok",
            app_env: "local",
            catalog_mode: "seed",
            llm_mode: "fake",
            cache_backend: "memory",
            session_backend: "sqlite",
            version: "0.1.0",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockRejectedValueOnce(new Error("connect ECONNREFUSED http://secret-backend.internal:9123"));

    vi.stubGlobal("fetch", fetchMock);

    const okRes = await healthGet(new NextRequest("http://localhost:3000/api/health"));
    expect(okRes.status).toBe(200);
    expect(okRes.headers.get("content-type")).toBe("application/json; charset=utf-8");
    expect(okRes.headers.get("x-content-type-options")).toBe("nosniff");
    expect(await okRes.json()).toMatchObject({ status: "ok", catalog_mode: "seed" });
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://secret-backend.internal:9123/health",
      expect.objectContaining({
        method: "GET",
        cache: "no-store",
        redirect: "error",
        signal: expect.any(AbortSignal),
      }),
    );

    for (const [method, handler] of [
      ["POST", healthPost],
      ["PUT", healthPut],
      ["PATCH", healthPatch],
      ["DELETE", healthDelete],
    ] as const) {
      const methodNotAllowed = await handler(
        new NextRequest("http://localhost:3000/api/health", {
          method,
          headers: { "X-Request-ID": `req-health-405-${method}` },
        }),
      );
      expect(methodNotAllowed.status).toBe(405);
      expect(methodNotAllowed.headers.get("allow")).toBe("GET");
      expect(methodNotAllowed.headers.get("x-request-id")).toBe(`req-health-405-${method}`);
      expect(methodNotAllowed.headers.get("x-content-type-options")).toBe("nosniff");
      expect(await methodNotAllowed.json()).toMatchObject({
        error_code: "method_not_allowed",
        retriable: false,
        request_id: `req-health-405-${method}`,
      });
    }

    const outageRes = await healthGet(
      new NextRequest("http://localhost:3000/api/health", {
        headers: { "X-Request-ID": "req-health-outage-1" },
      }),
    );
    expect(outageRes.status).toBe(503);
    expect(outageRes.headers.get("x-request-id")).toBe("req-health-outage-1");
    expect(outageRes.headers.get("content-type")).toBe("application/json; charset=utf-8");
    expect(outageRes.headers.get("x-content-type-options")).toBe("nosniff");
    const outageJson = (await outageRes.json()) as {
      error_code: string;
      message: string;
      retriable: boolean;
      request_id: string;
      details: unknown;
    };
    expect(outageJson).toMatchObject({
      error_code: "backend_unreachable",
      retriable: true,
      request_id: "req-health-outage-1",
      details: null,
    });
    expect(outageJson.message).not.toContain("secret-backend.internal");
    expect(outageJson.message).not.toContain("9123");
    expect(outageJson.message).not.toContain("ECONNREFUSED");
  });

  it("v1 proxy rejects empty/non-allowlisted paths, traversal segments, and wrong HTTP methods with X-Request-ID echo", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);

    const notFoundCases: Array<{ url: string; path: string[] }> = [
      { url: "http://localhost:3000/api/v1", path: [] },
      { url: "http://localhost:3000/api/v1/admin", path: ["admin"] },
      { url: "http://localhost:3000/api/v1/openapi.json", path: ["openapi.json"] },
      { url: "http://localhost:3000/api/v1/..", path: [".."] },
      { url: "http://localhost:3000/api/v1/%2e%2e", path: ["%2e%2e"] },
      { url: "http://localhost:3000/api/v1/markets/extra", path: ["markets", "extra"] },
    ];

    for (const testCase of notFoundCases) {
      const res = await v1Get(
        new NextRequest(testCase.url, {
          method: "GET",
          headers: { "X-Request-ID": "req-404-trace" },
        }),
        { params: Promise.resolve({ path: testCase.path }) },
      );
      expect(res.status).toBe(404);
      expect(res.headers.get("x-request-id")).toBe("req-404-trace");
      expect(res.headers.get("x-content-type-options")).toBe("nosniff");
      expect(await res.json()).toMatchObject({
        error_code: "route_not_found",
        retriable: false,
        request_id: "req-404-trace",
      });
    }

    const postMarkets = await v1Post(
      new NextRequest("http://localhost:3000/api/v1/markets", {
        method: "POST",
        headers: { "X-Request-ID": "req-405-mkt" },
      }),
      { params: Promise.resolve({ path: ["markets"] }) },
    );
    expect(postMarkets.status).toBe(405);
    expect(postMarkets.headers.get("allow")).toBe("GET");
    expect(postMarkets.headers.get("x-request-id")).toBe("req-405-mkt");
    expect(await postMarkets.json()).toMatchObject({
      error_code: "method_not_allowed",
      request_id: "req-405-mkt",
    });

    const getChat = await v1Get(
      new NextRequest("http://localhost:3000/api/v1/chat", { method: "GET" }),
      { params: Promise.resolve({ path: ["chat"] }) },
    );
    expect(getChat.status).toBe(405);
    expect(getChat.headers.get("allow")).toBe("POST");

    const patchChat = await v1Patch(
      new NextRequest("http://localhost:3000/api/v1/chat", {
        method: "PATCH",
        headers: { "X-Request-ID": "req-405-patch" },
      }),
      { params: Promise.resolve({ path: ["chat"] }) },
    );
    expect(patchChat.status).toBe(405);
    expect(patchChat.headers.get("allow")).toBe("POST");
    expect(patchChat.headers.get("x-request-id")).toBe("req-405-patch");

    const deleteSearch = await v1Delete(
      new NextRequest("http://localhost:3000/api/v1/search", { method: "DELETE" }),
      { params: Promise.resolve({ path: ["search"] }) },
    );
    expect(deleteSearch.status).toBe(405);
    expect(deleteSearch.headers.get("allow")).toBe("POST");

    const putChat = await v1Put(
      new NextRequest("http://localhost:3000/api/v1/chat", { method: "PUT" }),
      { params: Promise.resolve({ path: ["chat"] }) },
    );
    expect(putChat.status).toBe(405);
    expect(putChat.headers.get("allow")).toBe("POST");

    const headChat = await v1Head(
      new NextRequest("http://localhost:3000/api/v1/chat", { method: "HEAD" }),
      { params: Promise.resolve({ path: ["chat"] }) },
    );
    expect(headChat.status).toBe(405);
    expect(headChat.headers.get("allow")).toBe("POST");

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("v1 proxy returns sanitized 503 backend_unreachable on timeout, connection failure, redirect error, or invalid BACKEND_API_URL scheme", async () => {
    process.env.BACKEND_API_URL = "http://secret-internal-host:8000";

    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new Error("ECONNREFUSED http://secret-internal-host:8000/api/v1/chat"))
      .mockRejectedValueOnce(new DOMException("The operation was aborted due to timeout", "TimeoutError"))
      .mockRejectedValueOnce(new TypeError("redirect mode is set to error"));

    vi.stubGlobal("fetch", fetchMock);

    const requestIds = ["req-outage-conn", "req-outage-timeout", "req-outage-redirect"] as const;
    for (const reqId of requestIds) {
      const res = await v1Post(
        new NextRequest("http://localhost:3000/api/v1/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Request-ID": reqId,
          },
          body: JSON.stringify({ message: "anker" }),
        }),
        { params: Promise.resolve({ path: ["chat"] }) },
      );

      expect(res.status).toBe(503);
      expect(res.headers.get("x-request-id")).toBe(reqId);
      expect(res.headers.get("content-type")).toBe("application/json; charset=utf-8");
      expect(res.headers.get("x-content-type-options")).toBe("nosniff");
      const parsed = (await res.json()) as {
        error_code: string;
        message: string;
        retriable: boolean;
        request_id: string;
        details: unknown;
      };
      expect(parsed).toMatchObject({
        error_code: "backend_unreachable",
        retriable: true,
        request_id: reqId,
        details: null,
      });
      expect(parsed.message).not.toContain("secret-internal-host");
      expect(parsed.message).not.toContain("8000");
      expect(parsed.message).not.toContain("ECONNREFUSED");
      expect(parsed.message).not.toContain("TimeoutError");
      expect(parsed.message).not.toContain("redirect");
    }

    // Invalid URL scheme must fail closed with sanitized 503 without calling upstream fetch.
    const callsBeforeInvalidUrl = fetchMock.mock.calls.length;
    process.env.BACKEND_API_URL = "ftp://secret-internal-host:8000";
    const badSchemeRes = await v1Get(
      new NextRequest("http://localhost:3000/api/v1/markets", {
        method: "GET",
        headers: { "X-Request-ID": "req-bad-scheme" },
      }),
      { params: Promise.resolve({ path: ["markets"] }) },
    );
    expect(badSchemeRes.status).toBe(503);
    expect(badSchemeRes.headers.get("x-request-id")).toBe("req-bad-scheme");
    const badSchemeJson = (await badSchemeRes.json()) as {
      error_code: string;
      message: string;
      request_id: string;
    };
    expect(badSchemeJson).toMatchObject({
      error_code: "backend_unreachable",
      request_id: "req-bad-scheme",
    });
    expect(badSchemeJson.message).not.toContain("ftp://");
    expect(badSchemeJson.message).not.toContain("secret-internal-host");
    expect(fetchMock).toHaveBeenCalledTimes(callsBeforeInvalidUrl);
  });

  it("v1 proxy enforces JSON upstream responses, TRUST_PROXY_HEADERS IP validation, 64 KiB POST cap, malformed X-Request-ID replacement, and timeout/signal abort", async () => {
    process.env.BACKEND_API_URL = "http://runtime-backend.internal:8080";

    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response("<html><body>502 from nginx internal:8080</body></html>", {
          status: 200,
          headers: { "Content-Type": "text/html", "X-Request-ID": "up-html-200" },
        }),
      )
      .mockResolvedValueOnce(
        new Response("Traceback: internal:8080", {
          status: 500,
          headers: { "Content-Type": "text/plain" },
        }),
      )
      .mockResolvedValueOnce(
        new Response("{malformed-json", {
          status: 422,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    vi.stubGlobal("fetch", fetchMock);

    // 1. Non-JSON 200 -> sanitized 502 upstream_invalid_response + nosniff
    const htmlRes = await v1Get(
      new NextRequest("http://localhost:3000/api/v1/markets", {
        headers: { "X-Request-ID": "req-nonjson-200" },
      }),
      { params: Promise.resolve({ path: ["markets"] }) },
    );
    expect(htmlRes.status).toBe(502);
    expect(htmlRes.headers.get("content-type")).toBe("application/json; charset=utf-8");
    expect(htmlRes.headers.get("x-content-type-options")).toBe("nosniff");
    expect(htmlRes.headers.get("x-request-id")).toBe("up-html-200");
    const htmlJson = (await htmlRes.json()) as { error_code: string; message: string; retriable: boolean };
    expect(htmlJson).toMatchObject({
      error_code: "upstream_invalid_response",
      retriable: true,
    });
    expect(htmlJson.message).not.toContain("nginx");
    expect(htmlJson.message).not.toContain("8080");

    // 2. Non-JSON 500 -> sanitized 500 backend_unreachable + nosniff
    const text500Res = await v1Get(
      new NextRequest("http://localhost:3000/api/v1/markets", {
        headers: { "X-Request-ID": "req-nonjson-500" },
      }),
      { params: Promise.resolve({ path: ["markets"] }) },
    );
    expect(text500Res.status).toBe(500);
    expect(text500Res.headers.get("x-content-type-options")).toBe("nosniff");
    const text500Json = (await text500Res.json()) as { error_code: string; message: string; retriable: boolean };
    expect(text500Json).toMatchObject({
      error_code: "backend_unreachable",
      retriable: true,
      request_id: "req-nonjson-500",
    });
    expect(text500Json.message).not.toContain("Traceback");

    // 3. Malformed JSON with application/json content-type on < 500 -> sanitized 502 upstream_invalid_response
    const badJsonRes = await v1Get(
      new NextRequest("http://localhost:3000/api/v1/markets", {
        headers: { "X-Request-ID": "req-bad-json" },
      }),
      { params: Promise.resolve({ path: ["markets"] }) },
    );
    expect(badJsonRes.status).toBe(502);
    expect(await badJsonRes.json()).toMatchObject({
      error_code: "upstream_invalid_response",
      retriable: true,
      request_id: "req-bad-json",
    });

    // 4. Malformed X-Request-ID replaced with UUID + TRUST_PROXY_HEADERS=true forwards valid IPv4/IPv6 hops
    process.env.TRUST_PROXY_HEADERS = "true";
    const trustedRes = await v1Get(
      new NextRequest("http://localhost:3000/api/v1/markets", {
        headers: {
          "X-Request-ID": "invalid spaces & chars!",
          "X-Forwarded-For": "203.0.113.5, 2001:db8::1",
        },
      }),
      { params: Promise.resolve({ path: ["markets"] }) },
    );
    expect(trustedRes.status).toBe(200);
    const forwardedHeaders4 = fetchMock.mock.calls[3]?.[1]?.headers as Headers;
    expect(forwardedHeaders4.get("x-request-id")).toMatch(/^[0-9a-f-]{36}$/i);
    expect(trustedRes.headers.get("x-request-id")).toBe(forwardedHeaders4.get("x-request-id"));
    expect(forwardedHeaders4.get("x-forwarded-for")).toBe("203.0.113.5, 2001:db8::1");

    // 5. TRUST_PROXY_HEADERS=true drops X-Forwarded-For when any hop is invalid
    await v1Get(
      new NextRequest("http://localhost:3000/api/v1/markets", {
        headers: {
          "X-Request-ID": "req-bad-xff",
          "X-Forwarded-For": "203.0.113.5, spoofed.host",
        },
      }),
      { params: Promise.resolve({ path: ["markets"] }) },
    );
    const forwardedHeaders5 = fetchMock.mock.calls[4]?.[1]?.headers as Headers;
    expect(forwardedHeaders5.get("x-forwarded-for")).toBeNull();

    // 6. POST body size cap: exact 65536 bytes succeeds; > 65536 bytes (incl. multi-byte UTF-8) returns 413 with 0 fetch calls
    const exactPayload = JSON.stringify({ message: "a".repeat(65536 - '{"message":""}'.length) });
    expect(Buffer.byteLength(exactPayload, "utf8")).toBe(65536);
    const ok64kRes = await v1Post(
      new NextRequest("http://localhost:3000/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Request-ID": "req-64k-ok" },
        body: exactPayload,
      }),
      { params: Promise.resolve({ path: ["chat"] }) },
    );
    expect(ok64kRes.status).toBe(200);

    const callsBeforeOversized = fetchMock.mock.calls.length;
    const over64kRes = await v1Post(
      new NextRequest("http://localhost:3000/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Request-ID": "req-too-large" },
        body: JSON.stringify({ message: "س".repeat(33_000) }),
      }),
      { params: Promise.resolve({ path: ["chat"] }) },
    );
    expect(over64kRes.status).toBe(413);
    expect(over64kRes.headers.get("x-request-id")).toBe("req-too-large");
    expect(over64kRes.headers.get("x-content-type-options")).toBe("nosniff");
    expect(await over64kRes.json()).toMatchObject({
      error_code: "payload_too_large",
      retriable: false,
      request_id: "req-too-large",
    });
    expect(fetchMock).toHaveBeenCalledTimes(callsBeforeOversized);

    // 7. BACKEND_PROXY_TIMEOUT_MS validation/clamping & request.signal abort forwarding (incl. AbortSignal.any fallback)
    expect(resolveV1TimeoutMs()).toBe(12_000);
    process.env.BACKEND_PROXY_TIMEOUT_MS = "25000";
    expect(resolveV1TimeoutMs()).toBe(25_000);
    process.env.BACKEND_PROXY_TIMEOUT_MS = "250";
    expect(resolveV1TimeoutMs()).toBe(1_000);
    process.env.BACKEND_PROXY_TIMEOUT_MS = "120000";
    expect(resolveV1TimeoutMs()).toBe(60_000);
    process.env.BACKEND_PROXY_TIMEOUT_MS = "not-a-number";
    expect(resolveV1TimeoutMs()).toBe(12_000);

    const originalAny = AbortSignal.any;
    Object.defineProperty(AbortSignal, "any", {
      value: undefined,
      configurable: true,
      writable: true,
    });
    try {
      const reqAbortController = new AbortController();
      let capturedUpstreamSignal: AbortSignal | undefined;
      fetchMock.mockImplementationOnce(async (_url, init) => {
        capturedUpstreamSignal = init?.signal ?? undefined;
        reqAbortController.abort();
        throw new DOMException("Aborted", "AbortError");
      });

      const abortableReq = new NextRequest("http://localhost:3000/api/v1/markets", {
        headers: { "X-Request-ID": "req-abort-fallback" },
      });
      Object.defineProperty(abortableReq, "signal", {
        value: reqAbortController.signal,
        configurable: true,
      });

      const abortedRes = await v1Get(abortableReq, {
        params: Promise.resolve({ path: ["markets"] }),
      });
      expect(abortedRes.status).toBe(503);
      expect(capturedUpstreamSignal?.aborted).toBe(true);
    } finally {
      Object.defineProperty(AbortSignal, "any", {
        value: originalAny,
        configurable: true,
        writable: true,
      });
    }
  });
});
