import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiClientError,
  fetchHealth,
  fetchMarkets,
  searchOffers,
  sendChatTurn,
} from "@/lib/api";
import type {
  ChatResponse,
  HealthResponse,
  MarketsResponse,
  SearchResponse,
} from "@/lib/contracts";

function jsonResponse(body: unknown, status = 200, headers?: Record<string, string>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...(headers ?? {}),
    },
  });
}

describe("api client (unit & edge)", () => {
  const originalBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  beforeEach(() => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  });

  afterEach(() => {
    if (originalBaseUrl === undefined) {
      delete process.env.NEXT_PUBLIC_API_BASE_URL;
    } else {
      process.env.NEXT_PUBLIC_API_BASE_URL = originalBaseUrl;
    }
    vi.unstubAllGlobals();
  });

  it("typed client calls relative proxy routes and preserves DecimalString contracts", async () => {
    const marketsPayload: MarketsResponse = {
      markets: [
        {
          country: "EG",
          currency: "EGP",
          name_en: "Egypt",
          name_ar: "مصر",
          currency_label_en: "EGP",
          currency_label_ar: "جنيه مصري",
          serper_gl: "eg",
          stores: [
            { store_id: "noon", label_en: "Noon", label_ar: "نون", primary_domain: "noon.com" },
          ],
        },
      ],
      default_country: "EG",
      default_store: "both",
      request_id: "req-markets-1",
    };

    const healthPayload: HealthResponse = {
      status: "ok",
      app_env: "local",
      catalog_mode: "seed",
      llm_mode: "fake",
      cache_backend: "memory",
      session_backend: "sqlite",
      version: "0.1.0",
    };

    const chatPayload: ChatResponse = {
      session_id: "sess-1",
      status: "ok",
      reply: "تم العثور على أفضل العروض",
      action: "search",
      active_intent: {
        query: "Anker earbuds",
        country: "EG",
        store: "both",
        max_budget: "3500.00",
        min_rating: null,
        exclude_keywords: [],
        include_accessories: false,
        language: "ar",
      },
      top_offers: [
        {
          rank: 1,
          offer: {
            offer_id: "eg-noon-anker-l4nc",
            title: "Anker Soundcore Liberty 4 NC",
            price: "3299.00",
            currency: "EGP",
            store: "noon",
            country: "EG",
            url: "https://www.noon.com/egypt-ar/anker-l4nc/p/",
            rating: 4.7,
            review_count: 620,
            image_url: "https://f.nooncdn.com/p/anker.jpg",
            in_stock: true,
          },
          value_score: 88.5,
          price_norm: 0.72,
          bayesian_rating: 4.65,
          match_reasons: ["best_overall_value", "within_budget"],
        },
        {
          rank: 2,
          offer: {
            offer_id: "eg-amazon-anker-r50i",
            title: "Anker Soundcore R50i",
            price: "1199.00",
            currency: "EGP",
            store: "amazon",
            country: "EG",
            url: "https://www.amazon.eg/dp/B0C3ANKEG1",
            rating: 4.6,
            review_count: 890,
            image_url: null,
            in_stock: true,
          },
          value_score: 84.1,
          price_norm: 1.0,
          bayesian_rating: 4.58,
          match_reasons: ["lowest_price"],
        },
      ],
      ranking_result: {
        ranked_offers: [],
        total_candidates: 4,
        filtered_accessories_count: 1,
        filtered_outliers_count: 0,
        degraded_fewer_than_k: true,
      },
      telemetry: {
        llm_calls: 2,
        catalog_called: true,
        catalog_cache_hit: false,
        catalog_source_mode: "seed",
        used_rule_intent_fallback: false,
        used_template_summary: false,
        degraded_reason: null,
        latency_ms: 42.5,
      },
      request_id: "req-chat-1",
    };

    const searchPayload: SearchResponse = {
      intent: {
        query: "air fryer",
        country: "EG",
        store: "amazon",
        max_budget: "8000.00",
        min_rating: 4.0,
        exclude_keywords: [],
        include_accessories: false,
        language: "en",
      },
      ranking_result: {
        ranked_offers: [chatPayload.top_offers[0]!],
        total_candidates: 2,
        filtered_accessories_count: 0,
        filtered_outliers_count: 0,
        degraded_fewer_than_k: true,
      },
      source_mode: "seed",
      cache_hit: true,
      latency_ms: 11.2,
      request_id: "req-search-1",
    };

    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(marketsPayload))
      .mockResolvedValueOnce(jsonResponse(healthPayload))
      .mockResolvedValueOnce(jsonResponse(chatPayload))
      .mockResolvedValueOnce(jsonResponse(searchPayload));

    vi.stubGlobal("fetch", fetchMock);

    const abortController = new AbortController();
    const markets = await fetchMarkets(abortController.signal);
    const health = await fetchHealth();
    const chat = await sendChatTurn({
      message: "سماعة أنكر",
      country: "EG",
      store: "both",
      max_budget: "3500",
      language: "ar",
    });
    const search = await searchOffers({
      query: "air fryer",
      country: "EG",
      store: "amazon",
      max_budget: 8000,
      min_rating: 4.0,
      include_accessories: false,
      language: "en",
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/markets",
      expect.objectContaining({ method: "GET", signal: abortController.signal }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/health",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/v1/chat",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          message: "سماعة أنكر",
          country: "EG",
          store: "both",
          max_budget: "3500.00",
          language: "ar",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/v1/search",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          query: "air fryer",
          country: "EG",
          store: "amazon",
          max_budget: 8000,
          min_rating: 4.0,
          include_accessories: false,
          language: "en",
        }),
      }),
    );

    expect(markets.request_id).toBe("req-markets-1");
    expect(health.status).toBe("ok");
    expect(chat.top_offers[0]?.offer.price).toBe("3299.00");
    expect(chat.top_offers.map((item) => item.rank)).toEqual([1, 2]);
    expect(chat.active_intent?.max_budget).toBe("3500.00");
    expect(search.ranking_result.ranked_offers[0]?.offer.price).toBe("3299.00");
  });

  it("ApiClientError parses ErrorResponse, Retry-After, and non-JSON fallbacks", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error_code: "validation_error",
            message: "Invalid search parameters.",
            retriable: false,
            request_id: "req-422",
            details: [{ loc: ["body", "query"], msg: "String should have at least 1 character" }],
          },
          422,
          { "X-Request-ID": "req-422" },
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error_code: "rate_limit_exceeded",
            message: "Rate limit exceeded. Please retry later.",
            retriable: true,
            request_id: "req-429",
            details: null,
          },
          429,
          { "Retry-After": "45", "X-Request-ID": "req-429" },
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error_code: "backend_unreachable",
            message: "Backend service is temporarily unavailable.",
            retriable: true,
            request_id: "req-503",
            details: null,
          },
          503,
        ),
      )
      .mockResolvedValueOnce(
        new Response("<html><body>502 Bad Gateway</body></html>", {
          status: 502,
          headers: { "Content-Type": "text/html", "X-Request-ID": "req-502" },
        }),
      )
      .mockResolvedValueOnce(
        new Response("not-valid-json", {
          status: 200,
          headers: { "Content-Type": "text/plain", "X-Request-ID": "req-bad-200" },
        }),
      );

    vi.stubGlobal("fetch", fetchMock);

    await expect(sendChatTurn({ message: "test" })).rejects.toMatchObject({
      name: "ApiClientError",
      status: 422,
      errorCode: "validation_error",
      retriable: false,
      requestId: "req-422",
      retryAfterSeconds: null,
      details: [{ loc: ["body", "query"], msg: "String should have at least 1 character" }],
    });

    await expect(searchOffers({ query: "anker" })).rejects.toMatchObject({
      name: "ApiClientError",
      status: 429,
      errorCode: "rate_limit_exceeded",
      retriable: true,
      requestId: "req-429",
      retryAfterSeconds: 45,
    });

    await expect(fetchHealth()).rejects.toMatchObject({
      name: "ApiClientError",
      status: 503,
      errorCode: "backend_unreachable",
      retriable: true,
      requestId: "req-503",
    });

    await expect(fetchMarkets()).rejects.toMatchObject({
      name: "ApiClientError",
      status: 502,
      errorCode: "http_error",
      retriable: true,
      requestId: "req-502",
      details: null,
    });

    await expect(fetchMarkets()).rejects.toMatchObject({
      name: "ApiClientError",
      status: 200,
      errorCode: "invalid_json",
      retriable: false,
      requestId: "req-bad-200",
    });
  });

  it("api client validates max_budget bounds client-side and wraps fetch network errors", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);

    const invalidBudgets: Array<string | number> = [0, -10, 10_000_000.01, "0", "-5", "NaN", "1e50", ""];
    for (const badBudget of invalidBudgets) {
      await expect(
        sendChatTurn({ message: "earbuds", max_budget: badBudget }),
      ).rejects.toBeInstanceOf(ApiClientError);
      await expect(
        searchOffers({ query: "earbuds", max_budget: badBudget }),
      ).rejects.toMatchObject({
        status: 422,
        errorCode: "invalid_budget",
        retriable: false,
      });
    }

    expect(fetchMock).not.toHaveBeenCalled();

    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(fetchMarkets()).rejects.toMatchObject({
      name: "ApiClientError",
      status: 0,
      errorCode: "network_error",
      retriable: true,
    });

    fetchMock.mockRejectedValueOnce(new DOMException("The operation was aborted", "AbortError"));
    await expect(sendChatTurn({ message: "earbuds" })).rejects.toMatchObject({
      name: "ApiClientError",
      status: 0,
      errorCode: "network_error",
      retriable: true,
    });
  });

  it("api client handles explicit NEXT_PUBLIC_API_BASE_URL trailing slashes cleanly", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000///";

    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({
          markets: [],
          default_country: "EG",
          default_store: "both",
          request_id: "r1",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          status: "ok",
          app_env: "local",
          catalog_mode: "seed",
          llm_mode: "fake",
          cache_backend: "memory",
          session_backend: "sqlite",
          version: "0.1.0",
        }),
      );

    vi.stubGlobal("fetch", fetchMock);

    await fetchMarkets();
    await fetchHealth();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/markets",
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/health",
      expect.any(Object),
    );
  });
});
