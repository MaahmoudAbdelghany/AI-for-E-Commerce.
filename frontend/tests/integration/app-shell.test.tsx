import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/shell/AppShell";
import { ShopSessionProvider, useShopSession } from "@/context/ShopSessionContext";
import type { HealthResponse, MarketsResponse } from "@/lib/contracts";
import { MARKET_SESSIONS_STORAGE_KEY, PREFS_STORAGE_KEY } from "@/lib/storage";

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

function SessionProbe() {
  const { country, store, parsedMaxBudget, activeMarketSession, appendMarketTurn } = useShopSession();

  return (
    <div>
      <div data-testid="probe-country">{country}</div>
      <div data-testid="probe-store">{store}</div>
      <div data-testid="probe-budget">{parsedMaxBudget ?? "none"}</div>
      <div data-testid="probe-session-id">{activeMarketSession.sessionId ?? "null"}</div>
      <div data-testid="probe-messages-count">{activeMarketSession.messages.length}</div>
      <button
        type="button"
        onClick={() =>
          appendMarketTurn({
            sessionId: `sess-${country}`,
            userMessage: {
              id: `u-${country}`,
              role: "user",
              content: `query-${country}`,
              createdAtIso: "2026-11-16T20:00:00Z",
            },
          })
        }
      >
        Seed Active Turn
      </button>
    </div>
  );
}

function mockHealthyEndpoints() {
  return vi.fn<typeof fetch>().mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.endsWith("/api/v1/markets")) {
      return new Response(JSON.stringify(MOCK_MARKETS), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.endsWith("/api/health") || url.endsWith("/health")) {
      return new Response(JSON.stringify(MOCK_HEALTH), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("Not Found", { status: 404 });
  });
}

describe("AppShell & ShopSessionContext (integration)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("ShopSessionProvider hydrates markets/health, isolates EG/SA/AE sessions, and preserves sessionId on store/budget change", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockHealthyEndpoints());

    render(
      <ShopSessionProvider>
        <AppShell>
          <SessionProbe />
        </AppShell>
      </ShopSessionProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("متصل");
    });

    expect(screen.getByTestId("probe-country")).toHaveTextContent("EG");
    expect(screen.getByTestId("probe-store")).toHaveTextContent("both");
    expect(screen.getByTestId("probe-session-id")).toHaveTextContent("null");

    // Seed EG session
    await user.click(screen.getByRole("button", { name: "Seed Active Turn" }));
    expect(screen.getByTestId("probe-session-id")).toHaveTextContent("sess-EG");
    expect(screen.getByTestId("probe-messages-count")).toHaveTextContent("1");

    // Changing store and budget preserves EG sessionId
    await user.click(screen.getByRole("radio", { name: "نون" }));
    const budgetInput = screen.getByLabelText(/أقصى ميزانية/);
    await user.type(budgetInput, "2500");

    expect(screen.getByTestId("probe-store")).toHaveTextContent("noon");
    expect(screen.getByTestId("probe-budget")).toHaveTextContent("2500.00");
    expect(screen.getByTestId("probe-session-id")).toHaveTextContent("sess-EG");

    // Switch to Saudi Arabia -> isolated empty session
    await user.click(screen.getByRole("radio", { name: /السعودية/ }));
    expect(screen.getByTestId("probe-country")).toHaveTextContent("SA");
    expect(screen.getByTestId("probe-session-id")).toHaveTextContent("null");
    expect(screen.getByTestId("probe-messages-count")).toHaveTextContent("0");

    // Seed SA session, switch back to EG, then click New Chat (clears EG only)
    await user.click(screen.getByRole("button", { name: "Seed Active Turn" }));
    expect(screen.getByTestId("probe-session-id")).toHaveTextContent("sess-SA");

    await user.click(screen.getByRole("radio", { name: /مصر/ }));
    expect(screen.getByTestId("probe-session-id")).toHaveTextContent("sess-EG");

    await user.click(screen.getByRole("button", { name: /محادثة جديدة/ }));
    expect(screen.getByTestId("probe-session-id")).toHaveTextContent("null");
    expect(screen.getByTestId("probe-messages-count")).toHaveTextContent("0");

    // Verify SA session survived EG New Chat reset
    await user.click(screen.getByRole("radio", { name: /السعودية/ }));
    expect(screen.getByTestId("probe-session-id")).toHaveTextContent("sess-SA");
    expect(screen.getByTestId("probe-messages-count")).toHaveTextContent("1");
  });

  it("LanguageToggle switches dir=rtl/ltr and document lang without reload and renders RTL layout", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockHealthyEndpoints());

    render(
      <ShopSessionProvider>
        <AppShell>
          <SessionProbe />
        </AppShell>
      </ShopSessionProvider>,
    );

    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("مساعد التسوق الذكي");

    await user.click(screen.getByRole("button", { name: "تبديل اللغة" }));

    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Smart Shopping Advisor");
    expect(screen.getByRole("button", { name: /Start a new chat/i })).toHaveTextContent("New Chat");
    expect(JSON.parse(window.localStorage.getItem(PREFS_STORAGE_KEY) ?? "{}")).toMatchObject({
      language: "en",
    });

    await user.click(screen.getByRole("button", { name: "Switch language" }));
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("مساعد التسوق الذكي");
  });

  it("recovers from corrupted localStorage, renders MARKET_REGISTRY_FALLBACK on 503, and flags invalid budget", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(PREFS_STORAGE_KEY, "{corrupt");
    window.localStorage.setItem(MARKET_SESSIONS_STORAGE_KEY, "{corrupt");

    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(
          JSON.stringify({
            error_code: "backend_unreachable",
            message: "Backend service is temporarily unavailable.",
            retriable: true,
            request_id: "req-down",
            details: null,
          }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    render(
      <ShopSessionProvider>
        <AppShell>
          <SessionProbe />
        </AppShell>
      </ShopSessionProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/غير متصل/)).toBeInTheDocument();
      expect(screen.getByText(/عرض الأسواق الافتراضية/)).toBeInTheDocument();
    });

    // All 3 fallback markets remain interactive
    expect(screen.getByRole("radio", { name: /مصر/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /السعودية/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /الإمارات/ })).toBeInTheDocument();

    const budgetInput = screen.getByLabelText(/أقصى ميزانية/);
    await user.type(budgetInput, "-50");

    expect(budgetInput).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("أكبر من صفر");

    await user.click(screen.getByRole("button", { name: "مسح" }));
    expect(budgetInput).toHaveAttribute("aria-invalid", "false");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("HealthBadge displays degraded status and guards overlapping refreshHealth responses out of order", async () => {
    const user = userEvent.setup();
    let healthCall = 0;
    let resolveSlowRefresh!: (res: Response) => void;
    let slowSignal: AbortSignal | undefined;

    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation(async (input, init) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.endsWith("/api/v1/markets")) {
          return new Response(JSON.stringify(MOCK_MARKETS), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/api/health") || url.endsWith("/health")) {
          healthCall += 1;
          if (healthCall === 1) {
            return new Response(JSON.stringify({ ...MOCK_HEALTH, status: "degraded" }), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            });
          }
          if (healthCall === 2) {
            slowSignal = init?.signal ?? undefined;
            return new Promise<Response>((resolve) => {
              resolveSlowRefresh = resolve;
            });
          }
          return new Response(JSON.stringify({ ...MOCK_HEALTH, status: "ok" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response("Not Found", { status: 404 });
      }),
    );

    render(
      <ShopSessionProvider>
        <AppShell>
          <SessionProbe />
        </AppShell>
      </ShopSessionProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("تشغيل مقلّص");
    });

    const refreshBtn = screen.getByRole("button", { name: "تحديث حالة الخدمة" });
    await user.click(refreshBtn);
    await user.click(refreshBtn);

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("متصل");
    });
    expect(slowSignal?.aborted).toBe(true);

    // Even if the superseded request settled with degraded, latest "ok" must hold.
    resolveSlowRefresh(
      new Response(JSON.stringify({ ...MOCK_HEALTH, status: "degraded" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("متصل");
    });
  });
});
