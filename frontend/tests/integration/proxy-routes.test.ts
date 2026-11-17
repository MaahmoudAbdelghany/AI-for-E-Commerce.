import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  dynamic as healthDynamic,
  GET as healthGet,
  POST as healthPost,
} from "@/app/api/health/route";
import {
  DELETE as v1Delete,
  dynamic as v1Dynamic,
  GET as v1Get,
  HEAD as v1Head,
  POST as v1Post,
  PUT as v1Put,
} from "@/app/api/v1/[...path]/route";

describe("runtime proxy Route Handlers (integration & security)", () => {
  const originalBackendUrl = process.env.BACKEND_API_URL;

  afterEach(() => {
    if (originalBackendUrl === undefined) {
      delete process.env.BACKEND_API_URL;
    } else {
      process.env.BACKEND_API_URL = originalBackendUrl;
    }
    vi.unstubAllGlobals();
  });

  it("v1 proxy forwards allowlisted routes and passes upstream headers/status through", async () => {
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
              "Content-Type": "application/json",
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
    expect(await marketsRes.json()).toMatchObject({ request_id: "up-mkt-1" });

    const chatRes = await v1Post(
      new NextRequest("http://localhost:3000/api/v1/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": "client-req-2",
        },
        body: JSON.stringify({ message: "سماعة أنكر" }),
      }),
      { params: Promise.resolve({ path: ["chat"] }) },
    );

    expect(chatRes.status).toBe(429);
    expect(chatRes.headers.get("retry-after")).toBe("30");
    expect(chatRes.headers.get("x-request-id")).toBe("up-chat-429");

    const searchRes = await v1Post(
      new NextRequest("http://localhost:3000/api/v1/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: "   " }),
      }),
      { params: Promise.resolve({ path: ["search"] }) },
    );

    expect(searchRes.status).toBe(422);
    expect(await searchRes.json()).toMatchObject({ error_code: "validation_error" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://runtime-backend.internal:8080/api/v1/markets",
      expect.objectContaining({ method: "GET" }),
    );
    const firstHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(firstHeaders.get("accept")).toBe("application/json");
    expect(firstHeaders.get("x-request-id")).toBe("client-req-1");
    expect(firstHeaders.get("x-forwarded-for")).toBe("203.0.113.5");

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://runtime-backend.internal:8080/api/v1/chat",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://runtime-backend.internal:8080/api/v1/search",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("health proxy forwards runtime /health and maps outage to sanitized 503", async () => {
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
    expect(await okRes.json()).toMatchObject({ status: "ok", catalog_mode: "seed" });
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://secret-backend.internal:9123/health",
      expect.objectContaining({ method: "GET" }),
    );

    const methodNotAllowed = await healthPost(
      new NextRequest("http://localhost:3000/api/health", { method: "POST" }),
    );
    expect(methodNotAllowed.status).toBe(405);
    expect(methodNotAllowed.headers.get("allow")).toBe("GET");

    const outageRes = await healthGet(new NextRequest("http://localhost:3000/api/health"));
    expect(outageRes.status).toBe(503);
    const outageText = await outageRes.text();
    const outageJson = JSON.parse(outageText);
    expect(outageJson).toMatchObject({
      error_code: "backend_unreachable",
      retriable: true,
    });
    expect(outageText).not.toContain("secret-backend.internal");
    expect(outageText).not.toContain("9123");
    expect(outageText).not.toContain("ECONNREFUSED");
  });

  it("v1 proxy rejects non-allowlisted paths, traversal segments, and wrong HTTP methods", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);

    const notFoundCases: Array<{ url: string; path: string[] }> = [
      { url: "http://localhost:3000/api/v1/admin", path: ["admin"] },
      { url: "http://localhost:3000/api/v1/openapi.json", path: ["openapi.json"] },
      { url: "http://localhost:3000/api/v1/..", path: [".."] },
      { url: "http://localhost:3000/api/v1/%2e%2e", path: ["%2e%2e"] },
      { url: "http://localhost:3000/api/v1/markets/extra", path: ["markets", "extra"] },
    ];

    for (const testCase of notFoundCases) {
      const res = await v1Get(new NextRequest(testCase.url, { method: "GET" }), {
        params: Promise.resolve({ path: testCase.path }),
      });
      expect(res.status).toBe(404);
      expect(await res.json()).toMatchObject({
        error_code: "route_not_found",
        retriable: false,
      });
    }

    const postMarkets = await v1Post(
      new NextRequest("http://localhost:3000/api/v1/markets", { method: "POST" }),
      { params: Promise.resolve({ path: ["markets"] }) },
    );
    expect(postMarkets.status).toBe(405);
    expect(postMarkets.headers.get("allow")).toBe("GET");
    expect(await postMarkets.json()).toMatchObject({ error_code: "method_not_allowed" });

    const getChat = await v1Get(
      new NextRequest("http://localhost:3000/api/v1/chat", { method: "GET" }),
      { params: Promise.resolve({ path: ["chat"] }) },
    );
    expect(getChat.status).toBe(405);
    expect(getChat.headers.get("allow")).toBe("POST");

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

  it("v1 proxy returns sanitized 503 backend_unreachable on timeout or connection failure", async () => {
    process.env.BACKEND_API_URL = "http://secret-internal-host:8000";

    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new Error("ECONNREFUSED http://secret-internal-host:8000/api/v1/chat"))
      .mockRejectedValueOnce(new DOMException("The operation was aborted due to timeout", "TimeoutError"));

    vi.stubGlobal("fetch", fetchMock);

    for (let i = 0; i < 2; i += 1) {
      const res = await v1Post(
        new NextRequest("http://localhost:3000/api/v1/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: "anker" }),
        }),
        { params: Promise.resolve({ path: ["chat"] }) },
      );

      expect(res.status).toBe(503);
      const rawText = await res.text();
      const parsed = JSON.parse(rawText);
      expect(parsed).toMatchObject({
        error_code: "backend_unreachable",
        retriable: true,
      });
      expect(rawText).not.toContain("secret-internal-host");
      expect(rawText).not.toContain("8000");
      expect(rawText).not.toContain("ECONNREFUSED");
      expect(rawText).not.toContain("TimeoutError");
    }
  });
});
