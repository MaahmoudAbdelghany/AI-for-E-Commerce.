import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
  PATCH as v1Patch,
  POST as v1Post,
  PUT as v1Put,
} from "@/app/api/v1/[...path]/route";
import HomePage from "@/app/page";
import { ShopSessionProvider } from "@/context/ShopSessionContext";
import type {
  ChatRequest,
  ChatResponse,
  CountryCode,
  ErrorResponse,
  HealthResponse,
  MarketsResponse,
  RankedOffer,
  SearchRequest,
  SearchResponse,
} from "@/lib/contracts";
import { getDictionary, MATCH_REASON_LABELS, STARTER_PROMPTS } from "@/lib/i18n";
import { MARKET_SESSIONS_STORAGE_KEY, PREFS_STORAGE_KEY } from "@/lib/storage";

const UPSTREAM_BASE = "http://upstream-fastapi.internal:8000";

const MOCK_MARKETS: MarketsResponse = {
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
        { store_id: "amazon", label_en: "Amazon", label_ar: "أمازون", primary_domain: "amazon.eg" },
      ],
    },
    {
      country: "SA",
      currency: "SAR",
      name_en: "Saudi Arabia",
      name_ar: "السعودية",
      currency_label_en: "SAR",
      currency_label_ar: "ريال سعودي",
      serper_gl: "sa",
      stores: [
        { store_id: "noon", label_en: "Noon", label_ar: "نون", primary_domain: "noon.com" },
        { store_id: "amazon", label_en: "Amazon", label_ar: "أمازون", primary_domain: "amazon.sa" },
      ],
    },
    {
      country: "AE",
      currency: "AED",
      name_en: "United Arab Emirates",
      name_ar: "الإمارات",
      currency_label_en: "AED",
      currency_label_ar: "درهم إماراتي",
      serper_gl: "ae",
      stores: [
        { store_id: "noon", label_en: "Noon", label_ar: "نون", primary_domain: "noon.com" },
        { store_id: "amazon", label_en: "Amazon", label_ar: "أمازون", primary_domain: "amazon.ae" },
      ],
    },
  ],
  default_country: "EG",
  default_store: "both",
  request_id: "req-e2e-markets-1",
};

const MOCK_HEALTH: HealthResponse = {
  status: "ok",
  app_env: "local",
  catalog_mode: "seed",
  llm_mode: "fake",
  cache_backend: "memory",
  session_backend: "sqlite",
  version: "0.1.0",
};

function makeOffer(
  rank: number,
  id: string,
  title: string,
  price: string,
  store: "noon" | "amazon",
  country: CountryCode,
  overrides: Partial<RankedOffer["offer"]> & {
    value_score?: number;
    bayesian_rating?: number;
    match_reasons?: string[];
  } = {},
): RankedOffer {
  const currencyMap = { EG: "EGP", SA: "SAR", AE: "AED" } as const;
  const domainMap = {
    noon: "www.noon.com",
    amazon: country === "EG" ? "www.amazon.eg" : country === "SA" ? "www.amazon.sa" : "www.amazon.ae",
  } as const;

  return {
    rank,
    offer: {
      offer_id: id,
      title,
      price,
      currency: currencyMap[country],
      store,
      country,
      url: overrides.url ?? `https://${domainMap[store]}/item/${id}`,
      rating: overrides.rating !== undefined ? overrides.rating : 4.7,
      review_count: overrides.review_count !== undefined ? overrides.review_count : 320,
      image_url:
        overrides.image_url !== undefined
          ? overrides.image_url
          : `https://cdn.example.com/images/${id}.jpg`,
      in_stock: overrides.in_stock ?? true,
    },
    value_score: overrides.value_score ?? 92 - rank * 4,
    price_norm: 0.85,
    bayesian_rating: overrides.bayesian_rating ?? 4.66,
    match_reasons:
      overrides.match_reasons ??
      (rank === 1 ? ["best_overall_value", "within_budget"] : ["strong_value_runner_up"]),
  };
}

function makeChatResponse(overrides: Partial<ChatResponse> = {}): ChatResponse {
  const defaultOffers = [
    makeOffer(1, "eg-anker-1", "Anker Soundcore Liberty 4 NC", "3299.00", "noon", "EG", {
      match_reasons: ["best_overall_value", "top_bayesian_rating", "within_budget"],
    }),
    makeOffer(2, "eg-anker-2", "Anker Soundcore R50i", "1199.00", "amazon", "EG", {
      match_reasons: ["lowest_price", "high_review_confidence"],
    }),
    makeOffer(3, "eg-anker-3", "Anker Soundcore Life P3", "2450.00", "noon", "EG", {
      rating: null,
      review_count: 0,
      image_url: null,
      match_reasons: ["unrated_fallback", "strong_value_runner_up"],
    }),
  ];
  const topOffers = overrides.top_offers ?? defaultOffers;

  return {
    session_id: "sess-eg-e2e-1",
    status: "ok",
    reply: "إليك أفضل 3 عروض موثقة لسماعات أنكر في مصر.",
    action: "search",
    active_intent: {
      query: "Anker earbuds",
      country: "EG",
      store: "both",
      max_budget: null,
      min_rating: null,
      exclude_keywords: [],
      include_accessories: false,
      language: "ar",
    },
    top_offers: topOffers,
    ranking_result: {
      ranked_offers: topOffers,
      total_candidates: 8,
      filtered_accessories_count: 2,
      filtered_outliers_count: 1,
      degraded_fewer_than_k: false,
    },
    telemetry: {
      llm_calls: 2,
      catalog_called: true,
      catalog_cache_hit: false,
      catalog_source_mode: "seed",
      used_rule_intent_fallback: false,
      used_template_summary: false,
      degraded_reason: null,
      latency_ms: 42,
    },
    request_id: "req-e2e-chat-1",
    ...overrides,
  };
}

function makeSearchResponse(overrides: Partial<SearchResponse> = {}): SearchResponse {
  const offers = [
    makeOffer(1, "af-1", "Philips Essential Airfryer XL", "6999.00", "amazon", "EG", {
      match_reasons: ["best_overall_value", "high_review_confidence"],
    }),
    makeOffer(2, "af-2", "Ninja Air Fryer AF100", "7499.00", "noon", "EG", {
      image_url: "http://insecure.cdn.example.com/af-2.jpg",
      url: "javascript:alert(1)",
      match_reasons: ["strong_value_runner_up"],
    }),
  ];

  return {
    intent: {
      query: "air fryer",
      country: "EG",
      store: "both",
      max_budget: null,
      min_rating: 4.5,
      exclude_keywords: [],
      include_accessories: true,
      language: "ar",
    },
    ranking_result: {
      ranked_offers: offers,
      total_candidates: 5,
      filtered_accessories_count: 0,
      filtered_outliers_count: 1,
      degraded_fewer_than_k: true,
    },
    source_mode: "live",
    cache_hit: true,
    latency_ms: 14,
    request_id: "req-e2e-search-1",
    ...overrides,
  };
}

function jsonResponse(payload: unknown, status = 200, extraHeaders?: Record<string, string>): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...(extraHeaders ?? {}),
    },
  });
}

function resolveFetchUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") {
    return input;
  }
  if (input instanceof URL) {
    return input.toString();
  }
  return input.url;
}

function buildHeadersRecord(headers: HeadersInit | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  if (!headers) {
    return out;
  }
  new Headers(headers).forEach((value, key) => {
    out[key] = value;
  });
  return out;
}

type UpstreamDispatcher = (url: string, init?: RequestInit) => Promise<Response>;

function installFullStackRouteBridge(upstreamDispatcher: UpstreamDispatcher) {
  const upstreamSpy = vi.fn<UpstreamDispatcher>(upstreamDispatcher);

  const bridgeFetch = vi.fn<typeof fetch>(async (input, init) => {
    if (init?.signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }

    const url = resolveFetchUrl(input);

    // 1. Upstream calls issued by Next.js runtime Route Handlers (`lib/proxy.ts`).
    if (url.startsWith(UPSTREAM_BASE)) {
      return upstreamSpy(url, init);
    }

    // 2. Browser same-origin requests routed through REAL Next.js Route Handlers.
    const parsed = new URL(url, "http://localhost:3000");
    const method = (init?.method ?? "GET").toUpperCase();
    const requestHeaders = buildHeadersRecord(init?.headers);
    const bodyText = typeof init?.body === "string" ? init.body : undefined;

    const nextReq = new NextRequest(parsed.toString(), {
      method,
      headers: requestHeaders,
      ...(bodyText !== undefined && method !== "GET" && method !== "HEAD" ? { body: bodyText } : {}),
    });

    if (parsed.pathname === "/api/health") {
      if (method === "GET") {
        return healthGet(nextReq);
      }
      return healthPost(nextReq);
    }

    if (parsed.pathname.startsWith("/api/v1/")) {
      const suffix = parsed.pathname.slice("/api/v1/".length);
      const segments = suffix.length > 0 ? suffix.split("/") : [];
      const context = { params: Promise.resolve({ path: segments }) };

      switch (method) {
        case "GET":
          return v1Get(nextReq, context);
        case "POST":
          return v1Post(nextReq, context);
        case "PUT":
          return v1Put(nextReq, context);
        case "PATCH":
          return v1Patch(nextReq, context);
        case "DELETE":
          return v1Delete(nextReq, context);
        case "HEAD":
          return v1Head(nextReq, context);
        default:
          return v1Get(nextReq, context);
      }
    }

    throw new Error(`Unexpected live/unmocked fetch URL in offline Phase 3 E2E test: ${url}`);
  });

  vi.stubGlobal("fetch", bridgeFetch);
  return { bridgeFetch, upstreamSpy };
}

function renderFullApp() {
  return render(
    <ShopSessionProvider>
      <HomePage />
    </ShopSessionProvider>,
  );
}

describe("Phase 3 end-to-end integration (PI.1 — offline Route Handler round-trips)", () => {
  const originalBackendUrl = process.env.BACKEND_API_URL;

  beforeEach(() => {
    process.env.BACKEND_API_URL = UPSTREAM_BASE;
  });

  afterEach(() => {
    if (originalBackendUrl === undefined) {
      delete process.env.BACKEND_API_URL;
    } else {
      process.env.BACKEND_API_URL = originalBackendUrl;
    }
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("hydrates default Arabic RTL via real proxies, runs Chat search -> refine -> compare (0 catalog re-fetch, sourceMode=null), and toggles ar <-> en without reload", async () => {
    expect(v1Dynamic).toBe("force-dynamic");
    expect(healthDynamic).toBe("force-dynamic");

    const user = userEvent.setup();
    const arDict = getDictionary("ar");
    const enDict = getDictionary("en");
    const capturedChatPayloads: ChatRequest[] = [];
    let chatTurnIndex = 0;

    const refinedOffers = [
      makeOffer(1, "eg-noon-1", "Anker Soundcore R50i Noon", "1299.00", "noon", "EG", {
        match_reasons: ["best_overall_value", "within_budget"],
      }),
      makeOffer(2, "eg-noon-2", "Anker Soundcore Life P3 Noon", "2450.00", "noon", "EG", {
        match_reasons: ["top_bayesian_rating", "within_budget"],
      }),
    ];

    const { upstreamSpy } = installFullStackRouteBridge(async (url, init) => {
      if (url === `${UPSTREAM_BASE}/api/v1/markets`) {
        return jsonResponse(MOCK_MARKETS, 200, { "X-Request-ID": "req-e2e-markets-1" });
      }
      if (url === `${UPSTREAM_BASE}/health`) {
        return jsonResponse(MOCK_HEALTH, 200, { "X-Request-ID": "req-e2e-health-1" });
      }
      if (url === `${UPSTREAM_BASE}/api/v1/chat`) {
        const body = JSON.parse(String(init?.body ?? "{}")) as ChatRequest;
        capturedChatPayloads.push(body);
        chatTurnIndex += 1;

        if (chatTurnIndex === 1) {
          return jsonResponse(makeChatResponse(), 200, { "X-Request-ID": "req-e2e-chat-1" });
        }
        if (chatTurnIndex === 2) {
          return jsonResponse(
            makeChatResponse({
              session_id: "sess-eg-e2e-1",
              reply: "تمت تصفية العروض على متجر نون تحت 2600 جنيه.",
              action: "search",
              active_intent: {
                query: "Anker earbuds",
                country: "EG",
                store: "noon",
                max_budget: "2600.00",
                min_rating: null,
                exclude_keywords: [],
                include_accessories: false,
                language: "ar",
              },
              top_offers: refinedOffers,
              ranking_result: {
                ranked_offers: refinedOffers,
                total_candidates: 4,
                filtered_accessories_count: 1,
                filtered_outliers_count: 0,
                degraded_fewer_than_k: true,
              },
              telemetry: {
                llm_calls: 2,
                catalog_called: true,
                catalog_cache_hit: true,
                catalog_source_mode: "seed",
                used_rule_intent_fallback: false,
                used_template_summary: false,
                degraded_reason: null,
                latency_ms: 28,
              },
              request_id: "req-e2e-chat-2",
            }),
            200,
            { "X-Request-ID": "req-e2e-chat-2" },
          );
        }

        // Turn 3: Compare saved offers (0 catalog re-fetch, ranking_result=null, source_mode=null)
        return jsonResponse(
          makeChatResponse({
            session_id: "sess-eg-e2e-1",
            status: "ok",
            action: "compare",
            reply: "مقارنة سريعة للعرضين المتبقيين من نون بدون إعادة جلب الكتالوج.",
            active_intent: null,
            top_offers: refinedOffers,
            ranking_result: null,
            telemetry: {
              llm_calls: 1,
              catalog_called: false,
              catalog_cache_hit: false,
              catalog_source_mode: null,
              used_rule_intent_fallback: false,
              used_template_summary: true,
              degraded_reason: null,
              latency_ms: 17,
            },
            request_id: "req-e2e-compare-1",
          }),
          200,
          { "X-Request-ID": "req-e2e-compare-1" },
        );
      }

      throw new Error(`Unexpected upstream path: ${url}`);
    });

    renderFullApp();

    // 1. Default Arabic RTL hydration via real /api/v1/markets & /api/health proxies
    await waitFor(() => {
      expect(screen.getByRole("status", { name: /حالة الخدمة/ })).toHaveTextContent("متصل");
    });

    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByRole("radio", { name: /مصر/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: arDict.shell.stores.both })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByLabelText(/أقصى ميزانية \(جنيه مصري\)/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: arDict.workspace.chatModeLabel })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    // 2a. Chat Search via starter prompt
    const firstEgPrompt = STARTER_PROMPTS.EG[0];
    expect(firstEgPrompt).toBeDefined();
    await user.click(screen.getByRole("button", { name: firstEgPrompt!.labelAr }));

    await waitFor(() => {
      expect(screen.getByText("Anker Soundcore Liberty 4 NC")).toBeInTheDocument();
    });

    expect(capturedChatPayloads[0]).toMatchObject({
      message: firstEgPrompt!.queryAr,
      country: "EG",
      store: "both",
      language: "ar",
      session_id: null,
    });

    const comparisonPanel = document.getElementById("comparison-panel")!;
    const cardsAfterSearch = within(comparisonPanel).getAllByRole("article");
    expect(cardsAfterSearch).toHaveLength(3);
    expect(cardsAfterSearch[0]).toHaveTextContent("#1");
    expect(cardsAfterSearch[0]).toHaveTextContent("3,299.00 جنيه مصري");
    expect(cardsAfterSearch[1]).toHaveTextContent("#2");
    expect(cardsAfterSearch[1]).toHaveTextContent("1,199.00 جنيه مصري");
    expect(cardsAfterSearch[2]).toHaveTextContent("#3");
    expect(cardsAfterSearch[2]).toHaveTextContent(arDict.workspace.comparison.unratedBadge);
    expect(screen.getByText(arDict.workspace.telemetry.sourceSeed)).toBeInTheDocument();
    expect(screen.getByText("req-e2e-chat-1")).toBeInTheDocument();

    // 2b. Refine (store=noon, budget=2600) preserves session_id
    await user.click(screen.getByRole("radio", { name: arDict.shell.stores.noon }));
    const budgetInput = screen.getByLabelText(/أقصى ميزانية/);
    await user.type(budgetInput, "2600");

    const chatComposer = screen.getByLabelText(arDict.workspace.composer.chatLabel);
    await user.type(chatComposer, "أرخص سماعة أنكر من نون{Enter}");

    await waitFor(() => {
      expect(screen.getByText("Anker Soundcore R50i Noon")).toBeInTheDocument();
    });

    expect(capturedChatPayloads[1]).toMatchObject({
      message: "أرخص سماعة أنكر من نون",
      session_id: "sess-eg-e2e-1",
      country: "EG",
      store: "noon",
      max_budget: "2600.00",
      language: "ar",
    });
    expect(within(comparisonPanel).getAllByRole("article")).toHaveLength(2);
    expect(screen.getByText(arDict.workspace.banners.partialResultsTitle)).toBeInTheDocument();

    // 2c. Compare Saved Offers quick action (>= 2 offers, 0 catalog re-fetch, sourceMode=null)
    const compareBtn = screen.getByRole("button", {
      name: arDict.workspace.composer.compareSavedButton,
    });
    await user.click(compareBtn);

    await waitFor(() => {
      expect(screen.getByText("req-e2e-compare-1")).toBeInTheDocument();
    });

    expect(capturedChatPayloads[2]).toMatchObject({
      message: arDict.workspace.composer.compareSavedDefaultQuery,
      session_id: "sess-eg-e2e-1",
      country: "EG",
      store: "noon",
      max_budget: "2600.00",
    });
    expect(screen.getByText(arDict.workspace.telemetry.sourceSaved)).toBeInTheDocument();
    expect(within(comparisonPanel).getAllByRole("article")).toHaveLength(2);

    // Zero /api/v1/search calls occurred during Chat flow
    const calledUpstreamUrls = upstreamSpy.mock.calls.map((call) => call[0]);
    expect(calledUpstreamUrls.filter((u) => u.endsWith("/api/v1/search"))).toHaveLength(0);
    expect(calledUpstreamUrls.filter((u) => u.endsWith("/api/v1/chat"))).toHaveLength(3);

    // 4. Instant ar <-> en (dir="rtl" <-> dir="ltr") toggle without reload or extra network calls
    const upstreamCallsBeforeToggle = upstreamSpy.mock.calls.length;

    await user.click(screen.getByRole("button", { name: arDict.shell.languageToggleLabel }));

    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(enDict.brand.title);
    expect(screen.getByText(enDict.workspace.telemetry.sourceSaved)).toBeInTheDocument();
    expect(screen.getByText(MATCH_REASON_LABELS.best_overall_value.en)).toBeInTheDocument();

    const storeLinks = within(comparisonPanel).getAllByRole("link", {
      name: enDict.workspace.comparison.openStoreCta,
    });
    expect(storeLinks[0]).toHaveAttribute("target", "_blank");
    expect(storeLinks[0]).toHaveAttribute("rel", "noopener noreferrer");
    expect(storeLinks[0]?.getAttribute("href")).toMatch(/^https:\/\//);

    expect(JSON.parse(window.localStorage.getItem(PREFS_STORAGE_KEY) ?? "{}")).toMatchObject({
      country: "EG",
      store: "noon",
      language: "en",
    });
    expect(upstreamSpy).toHaveBeenCalledTimes(upstreamCallsBeforeToggle);

    // Toggle back to Arabic RTL
    await user.click(screen.getByRole("button", { name: enDict.shell.languageToggleLabel }));
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(arDict.brand.title);
    expect(upstreamSpy).toHaveBeenCalledTimes(upstreamCallsBeforeToggle);
  });

  it("executes Zero-LLM Direct Search (0 LLM calls, min_rating, include_accessories), enforces < 3 partial & 0-offer degradation, and handles rankingResult === null && sourceMode === null", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");
    const capturedSearchPayloads: SearchRequest[] = [];
    let searchCount = 0;

    const { upstreamSpy } = installFullStackRouteBridge(async (url, init) => {
      if (url === `${UPSTREAM_BASE}/api/v1/markets`) {
        return jsonResponse(MOCK_MARKETS);
      }
      if (url === `${UPSTREAM_BASE}/health`) {
        return jsonResponse(MOCK_HEALTH);
      }
      if (url === `${UPSTREAM_BASE}/api/v1/search`) {
        const payload = JSON.parse(String(init?.body ?? "{}")) as SearchRequest;
        capturedSearchPayloads.push(payload);
        searchCount += 1;

        if (searchCount === 1) {
          return jsonResponse(makeSearchResponse(), 200, { "X-Request-ID": "req-e2e-search-1" });
        }

        // Second search: 0 qualifying offers -> clears stale results honestly
        return jsonResponse(
          makeSearchResponse({
            intent: {
              query: payload.query,
              country: "EG",
              store: "both",
              max_budget: null,
              min_rating: 4.5,
              exclude_keywords: [],
              include_accessories: true,
              language: "ar",
            },
            ranking_result: {
              ranked_offers: [],
              total_candidates: 0,
              filtered_accessories_count: 0,
              filtered_outliers_count: 0,
              degraded_fewer_than_k: true,
            },
            cache_hit: false,
            request_id: "req-e2e-search-empty",
          }),
          200,
          { "X-Request-ID": "req-e2e-search-empty" },
        );
      }
      if (url === `${UPSTREAM_BASE}/api/v1/chat`) {
        // Explicit check for ranking_result === null AND catalog_source_mode === null with no prior rankingResult
        return jsonResponse(
          makeChatResponse({
            session_id: "sess-sa-null-rank",
            status: "ok",
            action: "compare",
            reply: "مقارنة بدون بيانات ترتيب إضافية.",
            active_intent: null,
            top_offers: [makeOffer(1, "sa-c1", "Anker SA Offer", "189.00", "noon", "SA")],
            ranking_result: null,
            telemetry: {
              llm_calls: 1,
              catalog_called: false,
              catalog_cache_hit: false,
              catalog_source_mode: null,
              used_rule_intent_fallback: false,
              used_template_summary: true,
              degraded_reason: null,
              latency_ms: 15,
            },
            request_id: "req-e2e-null-rank",
          }),
          200,
          { "X-Request-ID": "req-e2e-null-rank" },
        );
      }

      throw new Error(`Unexpected upstream path: ${url}`);
    });

    renderFullApp();

    await waitFor(() => {
      expect(screen.getByRole("status", { name: /حالة الخدمة/ })).toHaveTextContent("متصل");
    });

    // Switch to Zero-LLM Direct Search
    await user.click(screen.getByRole("tab", { name: arDict.workspace.searchModeLabel }));

    const queryInput = screen.getByLabelText(arDict.workspace.composer.searchLabel);
    const minRatingSelect = screen.getByLabelText(arDict.workspace.composer.minRatingLabel);
    const includeAccessories = screen.getByLabelText(
      arDict.workspace.composer.includeAccessoriesLabel,
    );
    const searchButton = screen.getByRole("button", {
      name: arDict.workspace.composer.searchButton,
    });

    await user.type(queryInput, "air fryer");
    await user.selectOptions(minRatingSelect, "4.5");
    await user.click(includeAccessories);
    await user.click(searchButton);

    await waitFor(() => {
      expect(screen.getByText("Philips Essential Airfryer XL")).toBeInTheDocument();
    });

    expect(capturedSearchPayloads[0]).toMatchObject({
      query: "air fryer",
      country: "EG",
      store: "both",
      min_rating: 4.5,
      include_accessories: true,
      language: "ar",
    });

    // 0 LLM calls in Direct Search and 0 /api/v1/chat upstream calls
    const upstreamUrls = upstreamSpy.mock.calls.map((c) => c[0]);
    expect(upstreamUrls.filter((u) => u.endsWith("/api/v1/chat"))).toHaveLength(0);

    const comparisonPanel = document.getElementById("comparison-panel")!;
    const telemetrySection = within(comparisonPanel).getByRole("region", {
      name: arDict.workspace.telemetry.title,
    });
    expect(within(telemetrySection).getByText(arDict.workspace.telemetry.sourceLive)).toBeInTheDocument();
    expect(within(telemetrySection).getByText(arDict.workspace.telemetry.cacheHit)).toBeInTheDocument();
    const llmCallsDt = within(telemetrySection).getByText(
      `${arDict.workspace.telemetry.llmCalls}:`,
    );
    expect(llmCallsDt.parentElement).not.toBeNull();
    expect(within(llmCallsDt.parentElement!).getByText("0")).toBeInTheDocument();
    expect(within(telemetrySection).getByText("req-e2e-search-1")).toBeInTheDocument();

    // Partial < 3 honest degradation + INV-09 unsafe URL/image defense
    const partialCards = within(comparisonPanel).getAllByRole("article");
    expect(partialCards).toHaveLength(2);
    expect(screen.getByText(arDict.workspace.banners.partialResultsTitle)).toBeInTheDocument();
    expect(
      within(partialCards[1]!).getByRole("button", {
        name: arDict.workspace.comparison.unavailableLinkCta,
      }),
    ).toBeDisabled();
    expect(
      within(partialCards[1]!).getByRole("img", {
        name: arDict.workspace.comparison.imageFallbackAlt,
      }),
    ).toBeInTheDocument();

    // 0-offer search clears stale cards honestly
    await user.clear(queryInput);
    await user.type(queryInput, "unavailable-sku-404");
    await user.click(searchButton);

    await waitFor(() => {
      expect(screen.getByText(arDict.workspace.banners.noResultsTitle)).toBeInTheDocument();
    });
    expect(within(comparisonPanel).queryByRole("article")).not.toBeInTheDocument();
    expect(screen.queryByText("Philips Essential Airfryer XL")).not.toBeInTheDocument();

    // Also verify rankingResult === null && sourceMode === null without prior rankingResult on SA
    await user.click(screen.getByRole("radio", { name: /السعودية/ }));
    await user.click(screen.getByRole("tab", { name: arDict.workspace.chatModeLabel }));
    await user.type(
      screen.getByLabelText(arDict.workspace.composer.chatLabel),
      "قارن عروض أنكر المحفوظة",
    );
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.sendButton }));

    await waitFor(() => {
      expect(screen.getByText("Anker SA Offer")).toBeInTheDocument();
    });
    expect(screen.getByText(arDict.workspace.telemetry.sourceSaved)).toBeInTheDocument();
    expect(screen.getByText("req-e2e-null-rank")).toBeInTheDocument();
    expect(screen.queryByText(arDict.workspace.telemetry.totalCandidates)).not.toBeInTheDocument();
  });

  it("isolates EG/SA/AE sessions and localStorage, enforces REFUSE PII non-persistence (INV-09), and resets only the active market on New Chat", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");
    const sensitiveCardInput = "بطاقة 4532015112830366 الرقم السري CVV 742";

    installFullStackRouteBridge(async (url, init) => {
      if (url === `${UPSTREAM_BASE}/api/v1/markets`) {
        return jsonResponse(MOCK_MARKETS);
      }
      if (url === `${UPSTREAM_BASE}/health`) {
        return jsonResponse(MOCK_HEALTH);
      }
      if (url === `${UPSTREAM_BASE}/api/v1/chat`) {
        const body = JSON.parse(String(init?.body ?? "{}")) as ChatRequest;
        const market = body.country ?? "EG";

        if (body.message.includes("4532015112830366")) {
          return jsonResponse(
            makeChatResponse({
              session_id: `sess-${market.toLowerCase()}-iso`,
              status: "refused",
              action: "refuse",
              reply: "تم رفض الطلب لاحتوائه على بيانات دفع حساسة.",
              active_intent: null,
              top_offers: [],
              ranking_result: null,
              telemetry: {
                llm_calls: 0,
                catalog_called: false,
                catalog_cache_hit: false,
                catalog_source_mode: null,
                used_rule_intent_fallback: false,
                used_template_summary: false,
                degraded_reason: "guardrail_refused",
                latency_ms: 4,
              },
              request_id: "req-e2e-refuse",
            }),
          );
        }

        const offerByMarket: Record<CountryCode, RankedOffer> = {
          EG: makeOffer(1, "eg-iso-1", "EG Galaxy Buds Offer", "2999.00", "noon", "EG"),
          SA: makeOffer(1, "sa-iso-1", "SA Anker Liberty Offer", "249.00", "amazon", "SA"),
          AE: makeOffer(1, "ae-iso-1", "AE Sony Earbuds Offer", "199.00", "noon", "AE"),
        };

        return jsonResponse(
          makeChatResponse({
            session_id: `sess-${market.toLowerCase()}-iso`,
            reply: `نتائج سوق ${market} جاهزة.`,
            top_offers: [offerByMarket[market]],
            ranking_result: {
              ranked_offers: [offerByMarket[market]],
              total_candidates: 1,
              filtered_accessories_count: 0,
              filtered_outliers_count: 0,
              degraded_fewer_than_k: true,
            },
            request_id: `req-${market.toLowerCase()}-iso`,
          }),
        );
      }

      throw new Error(`Unexpected upstream path: ${url}`);
    });

    renderFullApp();

    await waitFor(() => {
      expect(screen.getByRole("status", { name: /حالة الخدمة/ })).toHaveTextContent("متصل");
    });

    // Seed EG session
    await user.type(screen.getByLabelText(arDict.workspace.composer.chatLabel), "سماعة مصر");
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.sendButton }));
    await waitFor(() => expect(screen.getByText("EG Galaxy Buds Offer")).toBeInTheDocument());

    // Switch to SA -> clean slate, seed SA session
    await user.click(screen.getByRole("radio", { name: /السعودية/ }));
    expect(screen.queryByText("EG Galaxy Buds Offer")).not.toBeInTheDocument();
    expect(screen.getByText(arDict.workspace.emptyChatTitle)).toBeInTheDocument();

    await user.type(screen.getByLabelText(arDict.workspace.composer.chatLabel), "سماعة السعودية");
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.sendButton }));
    await waitFor(() => expect(screen.getByText("SA Anker Liberty Offer")).toBeInTheDocument());
    expect(screen.getByText("249.00 ريال سعودي")).toBeInTheDocument();

    // Switch to AE -> clean slate, seed AE session
    await user.click(screen.getByRole("radio", { name: /الإمارات/ }));
    expect(screen.queryByText("SA Anker Liberty Offer")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(arDict.workspace.composer.chatLabel), "سماعة الإمارات");
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.sendButton }));
    await waitFor(() => expect(screen.getByText("AE Sony Earbuds Offer")).toBeInTheDocument());
    expect(screen.getByText("199.00 درهم إماراتي")).toBeInTheDocument();

    // Send PII card input on AE -> REFUSE non-persistence & prior AE offer preserved (INV-09)
    await user.type(
      screen.getByLabelText(arDict.workspace.composer.chatLabel),
      sensitiveCardInput,
    );
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.sendButton }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(arDict.workspace.banners.refusedTitle);
    });
    expect(screen.getByText("AE Sony Earbuds Offer")).toBeInTheDocument();
    expect(screen.getByText(arDict.workspace.banners.redactedUserMessage)).toBeInTheDocument();
    expect(document.body.textContent ?? "").not.toContain("4532015112830366");
    expect(document.body.textContent ?? "").not.toContain("CVV 742");

    const storedAfterRefuse = window.localStorage.getItem(MARKET_SESSIONS_STORAGE_KEY) ?? "";
    expect(storedAfterRefuse).not.toContain("4532015112830366");
    expect(storedAfterRefuse).not.toContain("CVV 742");
    expect(storedAfterRefuse).toContain(arDict.workspace.banners.redactedUserMessage);

    // Verify all 3 isolated market sessions in localStorage
    const parsedBeforeReset = JSON.parse(storedAfterRefuse) as Record<
      CountryCode,
      { sessionId: string | null; messages: Array<{ content: string }> }
    >;
    expect(parsedBeforeReset.EG.sessionId).toBe("sess-eg-iso");
    expect(parsedBeforeReset.SA.sessionId).toBe("sess-sa-iso");
    expect(parsedBeforeReset.AE.sessionId).toBe("sess-ae-iso");

    // Switch back to EG and click New Chat -> resets ONLY EG
    await user.click(screen.getByRole("radio", { name: /مصر/ }));
    expect(screen.getByText("EG Galaxy Buds Offer")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: arDict.shell.newChatAria }));
    expect(screen.queryByText("EG Galaxy Buds Offer")).not.toBeInTheDocument();
    expect(screen.getByText(arDict.workspace.emptyChatTitle)).toBeInTheDocument();

    const parsedAfterReset = JSON.parse(
      window.localStorage.getItem(MARKET_SESSIONS_STORAGE_KEY) ?? "{}",
    ) as Record<CountryCode, { sessionId: string | null; messages: unknown[]; activeComparison: unknown }>;
    expect(parsedAfterReset.EG.sessionId).toBeNull();
    expect(parsedAfterReset.EG.messages).toHaveLength(0);
    expect(parsedAfterReset.EG.activeComparison).toBeNull();

    // SA and AE survived EG New Chat intact
    await user.click(screen.getByRole("radio", { name: /السعودية/ }));
    expect(screen.getByText("SA Anker Liberty Offer")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /الإمارات/ }));
    expect(screen.getByText("AE Sony Earbuds Offer")).toBeInTheDocument();
  });

  it("handles upstream 429 (Retry-After) and 503 backend_unreachable via real Route Handlers and recovers on Retry (INV-08)", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");
    let chatAttempt = 0;
    let healthDown = false;

    installFullStackRouteBridge(async (url) => {
      if (url === `${UPSTREAM_BASE}/api/v1/markets`) {
        return jsonResponse(MOCK_MARKETS);
      }
      if (url === `${UPSTREAM_BASE}/health`) {
        if (healthDown) {
          throw new Error(`connect ECONNREFUSED ${UPSTREAM_BASE}/health`);
        }
        return jsonResponse(MOCK_HEALTH);
      }
      if (url === `${UPSTREAM_BASE}/api/v1/chat`) {
        chatAttempt += 1;
        if (chatAttempt === 1) {
          const err429: ErrorResponse = {
            error_code: "rate_limit_exceeded",
            message: "Too many requests.",
            retriable: true,
            request_id: "req-e2e-429",
            details: null,
          };
          return jsonResponse(err429, 429, {
            "Retry-After": "12",
            "X-Request-ID": "req-e2e-429",
          });
        }
        if (chatAttempt === 2) {
          throw new Error(`connect ECONNREFUSED ${UPSTREAM_BASE}/api/v1/chat`);
        }
        return jsonResponse(
          makeChatResponse({
            session_id: "sess-recovered-e2e",
            reply: "تم الاسترداد وعرض أفضل العروض بنجاح.",
            request_id: "req-e2e-recovered",
          }),
          200,
          { "X-Request-ID": "req-e2e-recovered" },
        );
      }

      throw new Error(`Unexpected upstream path: ${url}`);
    });

    renderFullApp();

    await waitFor(() => {
      expect(screen.getByRole("status", { name: /حالة الخدمة/ })).toHaveTextContent("متصل");
    });

    // Attempt 1 -> upstream 429 passthrough through Route Handler
    await user.type(screen.getByLabelText(arDict.workspace.composer.chatLabel), "سماعة أنكر");
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.sendButton }));

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent("429");
      expect(alert).toHaveTextContent("12");
    });

    // Attempt 2 (Retry) -> upstream throws -> Route Handler maps to sanitized 503 backend_unreachable
    healthDown = true;
    await user.click(screen.getByRole("button", { name: arDict.workspace.banners.retryButton }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(arDict.workspace.banners.networkErrorTitle);
    });
    expect(document.body.textContent ?? "").not.toContain("upstream-fastapi.internal");
    expect(document.body.textContent ?? "").not.toContain("ECONNREFUSED");

    // Verify /api/health proxy also maps outage to offline badge cleanly
    await user.click(screen.getByRole("button", { name: arDict.shell.health.refreshAria }));
    await waitFor(() => {
      expect(screen.getByRole("status", { name: /حالة الخدمة/ })).toHaveTextContent("غير متصل");
    });

    // Attempt 3 (Retry) -> upstream recovers to 200 OK
    healthDown = false;
    await user.click(screen.getByRole("button", { name: arDict.shell.health.refreshAria }));
    await user.click(screen.getByRole("button", { name: arDict.workspace.banners.retryButton }));

    await waitFor(() => {
      expect(screen.getByText("تم الاسترداد وعرض أفضل العروض بنجاح.")).toBeInTheDocument();
    });
    expect(screen.getByText("Anker Soundcore Liberty 4 NC")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("status", { name: /حالة الخدمة/ })).toHaveTextContent("متصل");
    });
  });

  it("round-trips a mixed Arabic/English query through real Route Handlers with dir=auto bidi isolation", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");
    const mixedQuery = "أفضل سماعة Anker Soundcore تحت 3500 EGP";
    const mixedReply = "إليك أفضل سماعة Anker Soundcore Liberty 4 NC في مصر.";

    installFullStackRouteBridge(async (url, init) => {
      if (url === `${UPSTREAM_BASE}/api/v1/markets`) {
        return jsonResponse(MOCK_MARKETS);
      }
      if (url === `${UPSTREAM_BASE}/health`) {
        return jsonResponse(MOCK_HEALTH);
      }
      if (url === `${UPSTREAM_BASE}/api/v1/chat`) {
        const body = JSON.parse(String(init?.body ?? "{}")) as ChatRequest;
        expect(body.message).toBe(mixedQuery);
        return jsonResponse(
          makeChatResponse({
            session_id: "sess-bidi-e2e",
            reply: mixedReply,
            top_offers: [
              makeOffer(1, "eg-bidi-1", "سماعة أنكر Soundcore Liberty 4 NC", "3299.00", "noon", "EG"),
            ],
            request_id: "req-e2e-bidi",
          }),
          200,
          { "X-Request-ID": "req-e2e-bidi" },
        );
      }
      throw new Error(`Unexpected upstream path: ${url}`);
    });

    renderFullApp();

    await waitFor(() => {
      expect(screen.getByRole("status", { name: /حالة الخدمة/ })).toHaveTextContent("متصل");
    });

    const composer = screen.getByLabelText(arDict.workspace.composer.chatLabel);
    expect(composer).toHaveAttribute("dir", "auto");
    await user.type(composer, `${mixedQuery}{Enter}`);

    await waitFor(() => {
      expect(screen.getByText(mixedReply)).toBeInTheDocument();
    });

    expect(screen.getByText(mixedQuery)).toHaveAttribute("dir", "auto");
    expect(screen.getByText(mixedReply)).toHaveAttribute("dir", "auto");
    expect(
      screen.getByRole("heading", { level: 3, name: "سماعة أنكر Soundcore Liberty 4 NC" }),
    ).toHaveAttribute("dir", "auto");
  });
});
