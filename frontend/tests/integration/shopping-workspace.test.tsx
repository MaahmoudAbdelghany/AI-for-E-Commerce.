import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "@/app/page";
import { AppShell } from "@/components/shell/AppShell";
import { ShoppingWorkspace } from "@/components/workspace/ShoppingWorkspace";
import { ShopSessionProvider } from "@/context/ShopSessionContext";
import {
  ApiClientError,
  fetchHealth,
  fetchMarkets,
  searchOffers,
  sendChatTurn,
} from "@/lib/api";
import type {
  ChatResponse,
  CountryCode,
  HealthResponse,
  MarketsResponse,
  RankedOffer,
  SearchResponse,
} from "@/lib/contracts";
import { getDictionary, MATCH_REASON_LABELS, STARTER_PROMPTS } from "@/lib/i18n";
import { MARKET_SESSIONS_STORAGE_KEY } from "@/lib/storage";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchMarkets: vi.fn(),
    fetchHealth: vi.fn(),
    sendChatTurn: vi.fn(),
    searchOffers: vi.fn(),
  };
});

const mockedFetchMarkets = vi.mocked(fetchMarkets);
const mockedFetchHealth = vi.mocked(fetchHealth);
const mockedSendChatTurn = vi.mocked(sendChatTurn);
const mockedSearchOffers = vi.mocked(searchOffers);

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
  request_id: "req-markets-1",
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
  store: "noon" | "amazon" = "noon",
  country: CountryCode = "EG",
): RankedOffer {
  const currencyMap = { EG: "EGP", SA: "SAR", AE: "AED" } as const;
  return {
    rank,
    offer: {
      offer_id: id,
      title,
      price,
      currency: currencyMap[country],
      store,
      country,
      url: `https://www.${store === "noon" ? "noon.com" : "amazon.eg"}/item/${id}`,
      rating: 4.7,
      review_count: 350,
      image_url: `https://cdn.example.com/${id}.jpg`,
      in_stock: true,
    },
    value_score: 90 - rank * 3,
    price_norm: 0.8,
    bayesian_rating: 4.65,
    match_reasons: rank === 1 ? ["best_overall_value", "within_budget"] : ["strong_value_runner_up"],
  };
}

function makeTop3Offers(country: CountryCode = "EG"): RankedOffer[] {
  return [
    makeOffer(1, `${country}-1`, "Anker Soundcore Liberty 4 NC", "3299.00", "noon", country),
    makeOffer(2, `${country}-2`, "Anker Soundcore R50i", "1199.00", "amazon", country),
    makeOffer(3, `${country}-3`, "Anker Soundcore Life P3", "2450.00", "noon", country),
  ];
}

function makeChatResponse(overrides: Partial<ChatResponse> = {}): ChatResponse {
  const topOffers = overrides.top_offers ?? makeTop3Offers("EG");
  return {
    session_id: "sess-eg-1",
    status: "ok",
    reply: "إليك أفضل 3 عروض موثقة لسماعات أنكر.",
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
      latency_ms: 44,
    },
    request_id: "req-chat-1",
    ...overrides,
  };
}

function makeSearchResponse(overrides: Partial<SearchResponse> = {}): SearchResponse {
  const offers = makeTop3Offers("EG");
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
      total_candidates: 6,
      filtered_accessories_count: 0,
      filtered_outliers_count: 0,
      degraded_fewer_than_k: false,
    },
    source_mode: "seed",
    cache_hit: true,
    latency_ms: 12,
    request_id: "req-search-1",
    ...overrides,
  };
}

function renderWorkspaceWithShell() {
  return render(
    <ShopSessionProvider>
      <AppShell>
        <ShoppingWorkspace />
      </AppShell>
    </ShopSessionProvider>,
  );
}

describe("ShoppingWorkspace & HomePage (integration & edge)", () => {
  beforeEach(() => {
    mockedFetchMarkets.mockResolvedValue(MOCK_MARKETS);
    mockedFetchHealth.mockResolvedValue(MOCK_HEALTH);
    mockedSendChatTurn.mockReset();
    mockedSearchOffers.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("default chat mode starter prompts, Shift+Enter newline, and Enter/Send update ChatThread (dir=auto), Top-3 grid, telemetry, and session storage", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");

    mockedSendChatTurn
      .mockResolvedValueOnce(makeChatResponse())
      .mockResolvedValueOnce(
        makeChatResponse({
          session_id: "sess-eg-1",
          reply: "تم تحديث النتائج لميزانية أقل.",
          request_id: "req-chat-2",
        }),
      );

    renderWorkspaceWithShell();

    const firstPrompt = STARTER_PROMPTS.EG[0]!;
    await user.click(screen.getByRole("button", { name: firstPrompt.labelAr }));

    await waitFor(() => {
      expect(mockedSendChatTurn).toHaveBeenNthCalledWith(
        1,
        expect.objectContaining({
          message: firstPrompt.queryAr,
          country: "EG",
          store: "both",
          language: "ar",
        }),
        expect.any(AbortSignal),
      );
    });

    const userBubble = screen.getByText(firstPrompt.queryAr);
    const assistantBubble = screen.getByText("إليك أفضل 3 عروض موثقة لسماعات أنكر.");
    expect(userBubble).toHaveAttribute("dir", "auto");
    expect(assistantBubble).toHaveAttribute("dir", "auto");

    const topHeading = screen.getByRole("heading", {
      level: 3,
      name: "Anker Soundcore Liberty 4 NC",
    });
    expect(topHeading).toHaveAttribute("dir", "auto");
    expect(screen.getByText("Anker Soundcore R50i")).toBeInTheDocument();
    expect(screen.getByText("Anker Soundcore Life P3")).toBeInTheDocument();
    expect(screen.getByText(arDict.workspace.telemetry.sourceSeed)).toBeInTheDocument();
    expect(screen.getByText("req-chat-1")).toBeInTheDocument();

    // Shift+Enter inserts a newline without submitting; Enter submits follow-up
    const composer = screen.getByLabelText(arDict.workspace.composer.chatLabel);
    expect(composer).toHaveAttribute("dir", "auto");
    await user.type(composer, "أرخص سعر متاح{Shift>}{Enter}{/Shift}تحت 3000");
    expect(mockedSendChatTurn).toHaveBeenCalledTimes(1);
    expect(composer).toHaveValue("أرخص سعر متاح\nتحت 3000");
    await user.type(composer, "{Enter}");

    await waitFor(() => {
      expect(mockedSendChatTurn).toHaveBeenNthCalledWith(
        2,
        expect.objectContaining({
          message: "أرخص سعر متاح\nتحت 3000",
          session_id: "sess-eg-1",
          country: "EG",
        }),
        expect.any(AbortSignal),
      );
    });

    expect(screen.getByText("تم تحديث النتائج لميزانية أقل.")).toBeInTheDocument();

    const storedRaw = window.localStorage.getItem(MARKET_SESSIONS_STORAGE_KEY);
    expect(storedRaw).not.toBeNull();
    const stored = JSON.parse(storedRaw!);
    expect(stored.EG.sessionId).toBe("sess-eg-1");
    expect(stored.EG.messages).toHaveLength(4);
    expect(stored.EG.activeComparison.rankedOffers).toHaveLength(3);
  });

  it("ModeToggle switches to zero-LLM Direct Search (0 LLM calls) with min_rating/include_accessories and preserves existing chat thread", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");

    mockedSendChatTurn.mockResolvedValueOnce(
      makeChatResponse({
        session_id: "sess-preserve-thread",
        reply: "نتائج المحادثة المحفوظة",
      }),
    );

    mockedSearchOffers.mockResolvedValueOnce(
      makeSearchResponse({
        ranking_result: {
          ranked_offers: [
            makeOffer(1, "af-1", "Philips Essential Airfryer XL", "6999.00", "amazon", "EG"),
            makeOffer(2, "af-2", "Ninja Air Fryer AF100", "7499.00", "noon", "EG"),
          ],
          total_candidates: 5,
          filtered_accessories_count: 0,
          filtered_outliers_count: 1,
          degraded_fewer_than_k: true,
        },
        source_mode: "seed",
        cache_hit: true,
        latency_ms: 9,
        request_id: "req-search-airfryer",
      }),
    );

    renderWorkspaceWithShell();

    // Seed an existing chat thread first so we verify ModeToggle preserves it.
    const composer = screen.getByLabelText(arDict.workspace.composer.chatLabel);
    await user.type(composer, "سماعة أنكر{Enter}");
    await waitFor(() => expect(screen.getByText("نتائج المحادثة المحفوظة")).toBeInTheDocument());
    expect(mockedSendChatTurn).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("tab", { name: arDict.workspace.searchModeLabel }));

    const queryInput = screen.getByLabelText(arDict.workspace.composer.searchLabel);
    expect(queryInput).toHaveAttribute("dir", "auto");
    const minRatingSelect = screen.getByLabelText(arDict.workspace.composer.minRatingLabel);
    const accessoriesCheckbox = screen.getByLabelText(
      arDict.workspace.composer.includeAccessoriesLabel,
    );

    await user.type(queryInput, "air fryer");
    await user.selectOptions(minRatingSelect, "4.5");
    await user.click(accessoriesCheckbox);
    await user.click(
      screen.getByRole("button", { name: arDict.workspace.composer.searchButton }),
    );

    await waitFor(() => {
      expect(mockedSearchOffers).toHaveBeenCalledWith(
        expect.objectContaining({
          query: "air fryer",
          country: "EG",
          store: "both",
          min_rating: 4.5,
          include_accessories: true,
          language: "ar",
        }),
        expect.any(AbortSignal),
      );
    });
    expect(mockedSendChatTurn).toHaveBeenCalledTimes(1);

    expect(screen.getByText("Philips Essential Airfryer XL")).toBeInTheDocument();
    expect(screen.getByText("Ninja Air Fryer AF100")).toBeInTheDocument();
    expect(screen.getByText(arDict.workspace.telemetry.cacheHit)).toBeInTheDocument();
    expect(screen.getByText("req-search-airfryer")).toBeInTheDocument();

    const comparisonPanel = document.getElementById("comparison-panel")!;
    const telemetrySection = within(comparisonPanel).getByRole("region", {
      name: arDict.workspace.telemetry.title,
    });
    const llmCallsDt = within(telemetrySection).getByText(
      `${arDict.workspace.telemetry.llmCalls}:`,
    );
    expect(llmCallsDt.parentElement).not.toBeNull();
    expect(within(llmCallsDt.parentElement!).getByText("0")).toBeInTheDocument();

    // Switching back to Chat mode keeps both the unified comparison results and existing chat thread intact
    await user.click(screen.getByRole("tab", { name: arDict.workspace.chatModeLabel }));
    expect(screen.getByText("Philips Essential Airfryer XL")).toBeInTheDocument();
    expect(screen.getByText("سماعة أنكر")).toBeInTheDocument();
    expect(screen.getByText("نتائج المحادثة المحفوظة")).toBeInTheDocument();
  });

  it("Compare Saved Offers requires an active Chat sessionId with >= 2 offers and dispatches comparison chat turn cleanly", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");

    const singleOffer = [makeOffer(1, "single-1", "Single Earbud Offer", "1500.00")];
    const twoOffers = makeTop3Offers("EG").slice(0, 2);

    mockedSearchOffers.mockResolvedValueOnce(
      makeSearchResponse({
        ranking_result: {
          ranked_offers: twoOffers,
          total_candidates: 2,
          filtered_accessories_count: 0,
          filtered_outliers_count: 0,
          degraded_fewer_than_k: true,
        },
        request_id: "req-search-no-session",
      }),
    );

    mockedSendChatTurn
      .mockResolvedValueOnce(
        makeChatResponse({
          session_id: "sess-cmp",
          top_offers: singleOffer,
          ranking_result: {
            ranked_offers: singleOffer,
            total_candidates: 1,
            filtered_accessories_count: 0,
            filtered_outliers_count: 0,
            degraded_fewer_than_k: true,
          },
        }),
      )
      .mockResolvedValueOnce(
        makeChatResponse({
          session_id: "sess-cmp",
          top_offers: twoOffers,
          ranking_result: {
            ranked_offers: twoOffers,
            total_candidates: 2,
            filtered_accessories_count: 0,
            filtered_outliers_count: 0,
            degraded_fewer_than_k: true,
          },
        }),
      )
      .mockResolvedValueOnce(
        makeChatResponse({
          session_id: "sess-cmp",
          action: "compare",
          status: "ok",
          reply: "مقارنة تفصيلية بين العرضين المحفوظين.",
          active_intent: null,
          top_offers: twoOffers,
          ranking_result: null,
          telemetry: {
            llm_calls: 1,
            catalog_called: false,
            catalog_cache_hit: false,
            catalog_source_mode: null,
            used_rule_intent_fallback: false,
            used_template_summary: true,
            degraded_reason: null,
            latency_ms: 18,
          },
          request_id: "req-compare-1",
        }),
      );

    renderWorkspaceWithShell();

    // 0 offers initially -> absent
    expect(
      screen.queryByRole("button", { name: arDict.workspace.composer.compareSavedButton }),
    ).not.toBeInTheDocument();

    // 2 offers from Direct Search only (sessionId === null) -> still absent
    await user.click(screen.getByRole("tab", { name: arDict.workspace.searchModeLabel }));
    await user.type(screen.getByLabelText(arDict.workspace.composer.searchLabel), "anker");
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.searchButton }));
    await waitFor(() => expect(screen.getByText("req-search-no-session")).toBeInTheDocument());
    await user.click(screen.getByRole("tab", { name: arDict.workspace.chatModeLabel }));
    expect(
      screen.queryByRole("button", { name: arDict.workspace.composer.compareSavedButton }),
    ).not.toBeInTheDocument();

    // 1 offer in Chat -> still absent
    const composer = screen.getByLabelText(arDict.workspace.composer.chatLabel);
    await user.type(composer, "سماعة واحدة");
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.sendButton }));
    await waitFor(() => expect(screen.getByText("Single Earbud Offer")).toBeInTheDocument());
    expect(
      screen.queryByRole("button", { name: arDict.workspace.composer.compareSavedButton }),
    ).not.toBeInTheDocument();

    // 2 offers with active Chat sessionId -> button appears
    await user.type(composer, "سماعتين أنكر");
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.sendButton }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: arDict.workspace.composer.compareSavedButton }),
      ).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole("button", { name: arDict.workspace.composer.compareSavedButton }),
    );

    await waitFor(() => {
      expect(mockedSendChatTurn).toHaveBeenNthCalledWith(
        3,
        expect.objectContaining({
          message: arDict.workspace.composer.compareSavedDefaultQuery,
          session_id: "sess-cmp",
          country: "EG",
        }),
        expect.any(AbortSignal),
      );
    });

    expect(screen.getByText("مقارنة تفصيلية بين العرضين المحفوظين.")).toBeInTheDocument();
    expect(screen.getByText(arDict.workspace.telemetry.sourceSaved)).toBeInTheDocument();
    expect(screen.getByText("req-compare-1")).toBeInTheDocument();
  });

  it("per-market isolation separates EG/SA/AE threads and offers while instant ar/en toggle updates all workspace copy", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");
    const enDict = getDictionary("en");

    mockedSendChatTurn.mockResolvedValueOnce(
      makeChatResponse({
        session_id: "sess-eg-iso",
        reply: "نتائج مصر الجاهزة",
        top_offers: makeTop3Offers("EG"),
      }),
    );

    renderWorkspaceWithShell();

    await user.click(screen.getByRole("button", { name: STARTER_PROMPTS.EG[0]!.labelAr }));
    await waitFor(() => expect(screen.getByText("نتائج مصر الجاهزة")).toBeInTheDocument());
    expect(screen.getByText("Anker Soundcore Liberty 4 NC")).toBeInTheDocument();

    // Switch to SA -> independent empty thread & comparison state
    await user.click(screen.getByRole("radio", { name: /السعودية/ }));
    expect(screen.queryByText("نتائج مصر الجاهزة")).not.toBeInTheDocument();
    expect(screen.queryByText("Anker Soundcore Liberty 4 NC")).not.toBeInTheDocument();
    expect(screen.getByText(arDict.workspace.emptyChatTitle)).toBeInTheDocument();
    expect(screen.getByText(arDict.workspace.comparison.panelEmptyTitle)).toBeInTheDocument();

    // Toggle language from ar (RTL) to en (LTR) -> updates workspace copy without reload
    await user.click(screen.getByRole("button", { name: arDict.shell.languageToggleLabel }));
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
    expect(screen.getByText(enDict.workspace.emptyChatTitle)).toBeInTheDocument();
    expect(screen.getByText(enDict.workspace.comparison.panelEmptyTitle)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: STARTER_PROMPTS.SA[0]!.labelEn }),
    ).toBeInTheDocument();

    // Switch back to EG -> EG offers & match reason labels appear in English
    await user.click(screen.getByRole("radio", { name: /Egypt/ }));
    expect(screen.getByText("Anker Soundcore Liberty 4 NC")).toBeInTheDocument();
    expect(screen.getByText(MATCH_REASON_LABELS.best_overall_value.en)).toBeInTheDocument();
  });

  it("HomePage renders ShoppingWorkspace cleanly inside AppShell", async () => {
    const arDict = getDictionary("ar");
    render(
      <ShopSessionProvider>
        <HomePage />
      </ShopSessionProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("متصل");
    });

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(arDict.brand.title);
    expect(screen.getByRole("tablist", { name: arDict.workspace.modeToggleLabel })).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: arDict.workspace.starterPromptsTitle }),
    ).toBeInTheDocument();
    expect(document.getElementById("comparison-panel")).not.toBeNull();
  });

  it("inline budget and Direct Search query validation block invalid submissions with zero API calls", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");

    renderWorkspaceWithShell();

    const budgetInput = screen.getByLabelText(/أقصى ميزانية/);
    const composerInput = screen.getByLabelText(arDict.workspace.composer.chatLabel);
    const sendButton = screen.getByRole("button", { name: arDict.workspace.composer.sendButton });

    await user.type(composerInput, "سماعة أنكر");

    for (const badBudget of ["-5", "0", "10000001", "not-a-number"]) {
      await user.clear(budgetInput);
      await user.type(budgetInput, badBudget);
      await user.click(sendButton);

      expect(screen.getByText(arDict.workspace.composer.validationBudgetBlocked)).toBeInTheDocument();
    }

    await user.clear(budgetInput);

    // Switch to Direct Search and verify blank and 501-char queries are blocked
    await user.click(screen.getByRole("tab", { name: arDict.workspace.searchModeLabel }));
    const searchButton = screen.getByRole("button", {
      name: arDict.workspace.composer.searchButton,
    });
    const searchInput = screen.getByLabelText(arDict.workspace.composer.searchLabel);

    await user.click(searchButton);
    expect(screen.getByRole("alert")).toHaveTextContent(
      arDict.workspace.composer.validationQueryRequired,
    );

    await user.type(searchInput, "   ");
    await user.click(searchButton);
    expect(screen.getByRole("alert")).toHaveTextContent(
      arDict.workspace.composer.validationQueryRequired,
    );

    await user.clear(searchInput);
    fireEvent.change(searchInput, { target: { value: "a".repeat(501) } });
    await user.click(searchButton);
    expect(screen.getByRole("alert")).toHaveTextContent(
      arDict.workspace.composer.validationQueryTooLong,
    );

    fireEvent.change(searchInput, { target: { value: "air fryer \u202E" } });
    await user.click(searchButton);
    expect(screen.getByRole("alert")).toHaveTextContent(
      arDict.workspace.composer.validationQueryUnsafeChars,
    );

    // Also block valid search query if budget cap is invalid
    fireEvent.change(searchInput, { target: { value: "air fryer" } });
    fireEvent.change(budgetInput, { target: { value: "-10" } });
    await user.click(searchButton);
    expect(screen.getByText(arDict.workspace.composer.validationBudgetBlocked)).toBeInTheDocument();

    expect(mockedSendChatTurn).not.toHaveBeenCalled();
    expect(mockedSearchOffers).not.toHaveBeenCalled();
  });

  it("in-flight guard blocks duplicate submits and aborts/ignores stale Chat & Direct Search responses on market switch or New Chat", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");

    let capturedChatSignal: AbortSignal | undefined;
    let rejectDeferred!: (err: unknown) => void;
    mockedSendChatTurn.mockImplementationOnce((_payload, signal) => {
      capturedChatSignal = signal;
      return new Promise<ChatResponse>((_resolve, reject) => {
        rejectDeferred = reject;
        signal?.addEventListener("abort", () => {
          reject(
            new ApiClientError({
              status: 0,
              errorCode: "network_error",
              message: "Aborted",
              retriable: true,
            }),
          );
        });
      });
    });

    renderWorkspaceWithShell();

    const composer = screen.getByLabelText(arDict.workspace.composer.chatLabel);
    await user.type(composer, "سماعة أنكر");

    const sendButton = screen.getByRole("button", { name: arDict.workspace.composer.sendButton });
    await user.click(sendButton);

    expect(mockedSendChatTurn).toHaveBeenCalledTimes(1);
    expect(screen.getByText(arDict.workspace.loadingResponse)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: arDict.workspace.composer.sendingButton })).toBeDisabled();

    // Repeated Enter / disabled Send clicks must not trigger a second call
    await user.type(composer, "{Enter}");
    expect(mockedSendChatTurn).toHaveBeenCalledTimes(1);
    expect(capturedChatSignal?.aborted).toBe(false);

    // Switch country to AE while EG request is still in-flight -> aborts signal immediately
    await user.click(screen.getByRole("radio", { name: /الإمارات/ }));
    expect(capturedChatSignal?.aborted).toBe(true);

    // Settling the aborted EG promise must leave AE and EG clean with zero error banners
    rejectDeferred(new Error("late settle"));
    await waitFor(() => {
      expect(screen.queryByText(arDict.workspace.loadingResponse)).not.toBeInTheDocument();
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText(arDict.workspace.emptyChatTitle)).toBeInTheDocument();

    // Switch back to EG to confirm EG also stayed completely clean
    await user.click(screen.getByRole("radio", { name: /مصر/ }));
    expect(screen.getByText(arDict.workspace.emptyChatTitle)).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    // Switch to AE and verify New Chat also aborts/ignores stale in-flight chat turns
    await user.click(screen.getByRole("radio", { name: /الإمارات/ }));
    let capturedSecondSignal: AbortSignal | undefined;
    let resolveSecond!: (value: ChatResponse) => void;
    mockedSendChatTurn.mockImplementationOnce((_payload, signal) => {
      capturedSecondSignal = signal;
      return new Promise<ChatResponse>((resolve) => {
        resolveSecond = resolve;
      });
    });

    await user.type(screen.getByLabelText(arDict.workspace.composer.chatLabel), "آيفون 15");
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.sendButton }));
    expect(mockedSendChatTurn).toHaveBeenCalledTimes(2);

    await user.click(screen.getByRole("button", { name: arDict.shell.newChatAria }));
    expect(capturedSecondSignal?.aborted).toBe(true);
    resolveSecond(
      makeChatResponse({
        session_id: "sess-stale-ae",
        reply: "عرض متأخر بعد محادثة جديدة",
      }),
    );

    await waitFor(() => {
      expect(screen.queryByText(arDict.workspace.loadingResponse)).not.toBeInTheDocument();
    });
    expect(screen.queryByText("عرض متأخر بعد محادثة جديدة")).not.toBeInTheDocument();

    // Equivalent in-flight duplicate-submit & race-cancellation check for Direct Search (`searchOffers`)
    let capturedSearchSignal: AbortSignal | undefined;
    let resolveSearch!: (value: SearchResponse) => void;
    mockedSearchOffers.mockImplementationOnce((_payload, signal) => {
      capturedSearchSignal = signal;
      return new Promise<SearchResponse>((resolve) => {
        resolveSearch = resolve;
      });
    });

    await user.click(screen.getByRole("tab", { name: arDict.workspace.searchModeLabel }));
    const searchInput = screen.getByLabelText(arDict.workspace.composer.searchLabel);
    await user.type(searchInput, "air fryer");
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.searchButton }));

    expect(mockedSearchOffers).toHaveBeenCalledTimes(1);
    const searchSendingBtn = screen.getByRole("button", {
      name: arDict.workspace.composer.sendingButton,
    });
    expect(searchSendingBtn).toBeDisabled();
    fireEvent.submit(searchSendingBtn.closest("form")!);
    expect(mockedSearchOffers).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("radio", { name: /السعودية/ }));
    expect(capturedSearchSignal?.aborted).toBe(true);
    resolveSearch(
      makeSearchResponse({
        ranking_result: {
          ranked_offers: [makeOffer(1, "stale-sa", "Stale Search Product", "500.00", "noon", "AE")],
          total_candidates: 1,
          filtered_accessories_count: 0,
          filtered_outliers_count: 0,
          degraded_fewer_than_k: true,
        },
      }),
    );

    await waitFor(() => {
      expect(screen.queryByText("Stale Search Product")).not.toBeInTheDocument();
    });
    expect(screen.getByText(arDict.workspace.comparison.panelEmptyTitle)).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /الإمارات/ }));
    expect(screen.queryByText("Stale Search Product")).not.toBeInTheDocument();
  });

  it("handles clarify, off_topic, refused (clearing composer without PII persistence), degraded + Retry, and generic_error", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");

    mockedSendChatTurn
      .mockResolvedValueOnce(
        makeChatResponse({
          session_id: "sess-status",
          reply: "تمت إضافة العروض الأولية",
          top_offers: makeTop3Offers("EG"),
        }),
      )
      .mockResolvedValueOnce(
        makeChatResponse({
          session_id: "sess-status",
          status: "clarify",
          action: "clarify",
          reply: "ما نوع المنتج الذي تبحث عنه؟",
          active_intent: null,
          top_offers: [],
          ranking_result: null,
        }),
      )
      .mockResolvedValueOnce(
        makeChatResponse({
          session_id: "sess-status",
          status: "off_topic",
          action: "off_topic",
          reply: "أساعدك فقط في التسوق.",
          active_intent: null,
          top_offers: [],
          ranking_result: null,
        }),
      )
      .mockResolvedValueOnce(
        makeChatResponse({
          session_id: "sess-status",
          status: "refused",
          action: "refuse",
          reply: "عذراً، لا يمكن قبول بيانات البطاقات أو المعلومات الحساسة.",
          active_intent: null,
          top_offers: [],
          ranking_result: null,
        }),
      )
      .mockResolvedValueOnce(
        makeChatResponse({
          session_id: "sess-status",
          status: "degraded",
          action: "search",
          reply: "تعذر الوصول لمزود العروض مؤقتاً.",
          active_intent: null,
          top_offers: [],
          ranking_result: null,
          telemetry: {
            llm_calls: 1,
            catalog_called: true,
            catalog_cache_hit: false,
            catalog_source_mode: null,
            used_rule_intent_fallback: false,
            used_template_summary: true,
            degraded_reason: "catalog_provider_error:serper",
            latency_ms: 85,
          },
        }),
      )
      .mockResolvedValueOnce(
        makeChatResponse({
          session_id: "sess-status",
          status: "ok",
          action: "search",
          reply: "تم استعادة عروض اللابتوب.",
          top_offers: [makeOffer(1, "laptop-1", "Lenovo IdeaPad Laptop", "18500.00", "noon", "EG")],
        }),
      )
      .mockRejectedValueOnce(
        new ApiClientError({
          status: 422,
          errorCode: "validation_error",
          message: "Unexpected validation failure from API.",
          retriable: false,
          requestId: "req-422-gen",
        }),
      );

    renderWorkspaceWithShell();

    const composer = screen.getByLabelText(arDict.workspace.composer.chatLabel);
    const sendButton = screen.getByRole("button", { name: arDict.workspace.composer.sendButton });

    // 1. Nominal search loads Top-3
    await user.type(composer, "سماعة أنكر");
    await user.click(sendButton);
    await waitFor(() =>
      expect(screen.getByText("Anker Soundcore Liberty 4 NC")).toBeInTheDocument(),
    );

    // 2. Clarify preserves prior Top-3 offers and shows clarify banner
    await user.type(composer, "أفضل");
    await user.click(sendButton);
    await waitFor(() =>
      expect(screen.getByText(arDict.workspace.banners.clarifyTitle)).toBeInTheDocument(),
    );
    expect(screen.getByText("Anker Soundcore Liberty 4 NC")).toBeInTheDocument();

    // 3. Off-topic preserves prior Top-3 offers and shows off-topic banner
    await user.type(composer, "حالة الطقس");
    await user.click(sendButton);
    await waitFor(() =>
      expect(screen.getByText(arDict.workspace.banners.offTopicTitle)).toBeInTheDocument(),
    );
    expect(screen.getByText("Anker Soundcore Liberty 4 NC")).toBeInTheDocument();

    // 4. Refused PII input: clears composer, preserves prior offers, shows refused alert, and never echoes/stores PII
    await user.type(composer, "4111111111111111");
    await user.click(sendButton);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(arDict.workspace.banners.refusedTitle),
    );
    expect(composer).toHaveValue("");
    expect(screen.getByText("Anker Soundcore Liberty 4 NC")).toBeInTheDocument();
    expect(screen.queryByText(/4111111111111111/)).not.toBeInTheDocument();

    const persistedRaw = window.localStorage.getItem(MARKET_SESSIONS_STORAGE_KEY) ?? "";
    expect(persistedRaw).not.toContain("4111111111111111");
    expect(persistedRaw).toContain(arDict.workspace.banners.redactedUserMessage);

    // 5. Degraded state renders degraded alert + Retry button -> Retry recovers cleanly
    await user.type(composer, "لابتوب");
    await user.click(sendButton);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(arDict.workspace.banners.degradedTitle),
    );
    await user.click(screen.getByRole("button", { name: arDict.workspace.banners.retryButton }));
    await waitFor(() =>
      expect(screen.getByText("Lenovo IdeaPad Laptop")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    // 6. generic_error renders non-retriable alert cleanly without Retry button
    await user.type(composer, "استعلام خاطئ");
    await user.click(sendButton);
    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent("Unexpected validation failure from API.");
    });
    expect(
      screen.queryByRole("button", { name: arDict.workspace.banners.retryButton }),
    ).not.toBeInTheDocument();
  });

  it("renders partial < 3 offers without fake padding and clears stale offers on 0 results", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");

    const twoOffers = makeTop3Offers("EG").slice(0, 2);
    mockedSearchOffers
      .mockResolvedValueOnce(
        makeSearchResponse({
          ranking_result: {
            ranked_offers: twoOffers,
            total_candidates: 3,
            filtered_accessories_count: 1,
            filtered_outliers_count: 0,
            degraded_fewer_than_k: true,
          },
        }),
      )
      .mockResolvedValueOnce(
        makeSearchResponse({
          ranking_result: {
            ranked_offers: [],
            total_candidates: 0,
            filtered_accessories_count: 0,
            filtered_outliers_count: 0,
            degraded_fewer_than_k: true,
          },
        }),
      );

    renderWorkspaceWithShell();

    await user.click(screen.getByRole("tab", { name: arDict.workspace.searchModeLabel }));
    const searchInput = screen.getByLabelText(arDict.workspace.composer.searchLabel);
    const searchButton = screen.getByRole("button", {
      name: arDict.workspace.composer.searchButton,
    });

    await user.type(searchInput, "air fryer");
    await user.click(searchButton);

    await waitFor(() => {
      const panel = document.getElementById("comparison-panel")!;
      expect(within(panel).getAllByRole("article")).toHaveLength(2);
    });
    expect(screen.getByText(arDict.workspace.banners.partialResultsTitle)).toBeInTheDocument();

    await user.clear(searchInput);
    await user.type(searchInput, "nonexistent-item-xyz");
    await user.click(searchButton);

    await waitFor(() => {
      expect(screen.getByText(arDict.workspace.banners.noResultsTitle)).toBeInTheDocument();
    });
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    expect(screen.queryByText("Anker Soundcore Liberty 4 NC")).not.toBeInTheDocument();
  });

  it("displays 429 Retry-After and 503 outage banners in Chat & Direct Search and recovers via Retry action", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");

    mockedSendChatTurn
      .mockRejectedValueOnce(
        new ApiClientError({
          status: 429,
          errorCode: "rate_limit_exceeded",
          message: "Rate limit exceeded.",
          retriable: true,
          requestId: "req-429",
          retryAfterSeconds: 15,
        }),
      )
      .mockRejectedValueOnce(
        new ApiClientError({
          status: 503,
          errorCode: "backend_unreachable",
          message: "Backend service unavailable.",
          retriable: true,
          requestId: "req-503",
        }),
      )
      .mockResolvedValueOnce(
        makeChatResponse({
          session_id: "sess-recovered",
          reply: "تم الاسترداد وعرض أفضل 3 عروض.",
          top_offers: makeTop3Offers("EG"),
        }),
      );

    mockedSearchOffers
      .mockRejectedValueOnce(
        new ApiClientError({
          status: 503,
          errorCode: "backend_unreachable",
          message: "Backend service unavailable.",
          retriable: true,
          requestId: "req-search-503",
        }),
      )
      .mockResolvedValueOnce(
        makeSearchResponse({
          ranking_result: {
            ranked_offers: [makeOffer(1, "search-rec-1", "Recovered Direct Offer", "1599.00", "noon", "EG")],
            total_candidates: 1,
            filtered_accessories_count: 0,
            filtered_outliers_count: 0,
            degraded_fewer_than_k: true,
          },
          request_id: "req-search-rec",
        }),
      );

    renderWorkspaceWithShell();

    const composer = screen.getByLabelText(arDict.workspace.composer.chatLabel);
    await user.type(composer, "سماعة أنكر");
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.sendButton }));

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent("429");
      expect(alert).toHaveTextContent("15");
    });

    // Retry #1 -> 503 backend_unreachable
    await user.click(screen.getByRole("button", { name: arDict.workspace.banners.retryButton }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        arDict.workspace.banners.networkErrorTitle,
      );
    });

    // Retry #2 -> 200 recovered Top-3 offers
    await user.click(screen.getByRole("button", { name: arDict.workspace.banners.retryButton }));
    await waitFor(() => {
      expect(screen.getByText("تم الاسترداد وعرض أفضل 3 عروض.")).toBeInTheDocument();
    });
    expect(screen.getByText("Anker Soundcore Liberty 4 NC")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    // Switch to Direct Search -> 503 -> Retry -> 200 recovery
    await user.click(screen.getByRole("tab", { name: arDict.workspace.searchModeLabel }));
    await user.type(screen.getByLabelText(arDict.workspace.composer.searchLabel), "air fryer");
    await user.click(screen.getByRole("button", { name: arDict.workspace.composer.searchButton }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        arDict.workspace.banners.networkErrorTitle,
      );
    });
    await user.click(screen.getByRole("button", { name: arDict.workspace.banners.retryButton }));
    await waitFor(() => {
      expect(screen.getByText("Recovered Direct Offer")).toBeInTheDocument();
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("handles mixed Arabic/English query with dir=auto bidi isolation across ChatThread, MessageComposer, and OfferCard", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");
    const mixedQuery = "أفضل سماعة Anker Soundcore تحت 3500 EGP";

    mockedSendChatTurn.mockResolvedValueOnce(
      makeChatResponse({
        session_id: "sess-bidi",
        reply: "تم العثور على Anker Soundcore R50i بسعر ممتاز.",
        top_offers: [
          makeOffer(1, "bidi-1", "سماعة أنكر Soundcore Liberty 4 NC", "3299.00", "noon", "EG"),
        ],
      }),
    );

    renderWorkspaceWithShell();

    const composer = screen.getByLabelText(arDict.workspace.composer.chatLabel);
    expect(composer).toHaveAttribute("dir", "auto");
    await user.type(composer, `${mixedQuery}{Enter}`);

    await waitFor(() => {
      expect(mockedSendChatTurn).toHaveBeenCalledWith(
        expect.objectContaining({ message: mixedQuery }),
        expect.any(AbortSignal),
      );
    });

    expect(screen.getByText(mixedQuery)).toHaveAttribute("dir", "auto");
    expect(screen.getByText("تم العثور على Anker Soundcore R50i بسعر ممتاز.")).toHaveAttribute(
      "dir",
      "auto",
    );
    const mixedCardHeading = screen.getByRole("heading", {
      level: 3,
      name: "سماعة أنكر Soundcore Liberty 4 NC",
    });
    expect(mixedCardHeading).toHaveAttribute("dir", "auto");
  });
});
