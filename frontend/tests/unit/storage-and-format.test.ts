import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ActiveComparisonState,
  CountryCode,
  MatchReasonCode,
  TurnAction,
  TurnStatus,
} from "@/lib/contracts";
import {
  formatBayesianScore,
  formatExactPrice,
  formatLatencyMs,
  formatRatingValue,
  formatValueScore,
  sanitizeHttpsUrl,
  validateBudgetInput,
} from "@/lib/format";
import {
  getDictionary,
  getMatchReasonLabel,
  MATCH_REASON_LABELS,
  STARTER_PROMPTS,
} from "@/lib/i18n";
import {
  clearMarketSession,
  DEFAULT_USER_PREFERENCES,
  loadMarketSessions,
  loadPreferences,
  MARKET_SESSIONS_STORAGE_KEY,
  PREFS_STORAGE_KEY,
  saveMarketSessions,
  savePreferences,
} from "@/lib/storage";

const ALL_MATCH_REASONS: MatchReasonCode[] = [
  "best_overall_value",
  "lowest_price",
  "top_bayesian_rating",
  "high_review_confidence",
  "within_budget",
  "unrated_fallback",
  "strong_value_runner_up",
];

const ALL_TURN_ACTIONS: TurnAction[] = ["search", "compare", "clarify", "off_topic", "refuse"];
const ALL_TURN_STATUSES: TurnStatus[] = ["ok", "clarify", "off_topic", "refused", "degraded"];

describe("format, i18n, and storage (unit & edge)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("formatExactPrice preserves Decimal digits, i18n covers all codes, and sanitizeHttpsUrl enforces https", () => {
    expect(formatExactPrice("3299.00", "EGP", "en")).toBe("3,299.00 EGP");
    expect(formatExactPrice("3299.00", "EGP", "ar")).toBe("3,299.00 جنيه مصري");
    expect(formatExactPrice("9999999.99", "SAR", "en")).toBe("9,999,999.99 SAR");
    // Verifies string-based formatting with zero IEEE-754 float precision drift on >53-bit digits
    expect(formatExactPrice("123456789012345678.95", "AED", "en")).toBe(
      "123,456,789,012,345,678.95 AED",
    );

    const arDict = getDictionary("ar");
    const enDict = getDictionary("en");
    for (const reason of ALL_MATCH_REASONS) {
      expect(MATCH_REASON_LABELS[reason].ar.length).toBeGreaterThan(0);
      expect(MATCH_REASON_LABELS[reason].en.length).toBeGreaterThan(0);
      expect(arDict.workspace.matchReasons[reason]).toBe(MATCH_REASON_LABELS[reason].ar);
      expect(enDict.workspace.matchReasons[reason]).toBe(MATCH_REASON_LABELS[reason].en);
      expect(getMatchReasonLabel(reason, "ar")).toBe(MATCH_REASON_LABELS[reason].ar);
      expect(getMatchReasonLabel(reason, "en")).toBe(MATCH_REASON_LABELS[reason].en);
    }

    for (const action of ALL_TURN_ACTIONS) {
      expect(arDict.workspace.turnActions[action].length).toBeGreaterThan(0);
      expect(enDict.workspace.turnActions[action].length).toBeGreaterThan(0);
    }
    for (const status of ALL_TURN_STATUSES) {
      expect(arDict.workspace.turnStatuses[status].length).toBeGreaterThan(0);
      expect(enDict.workspace.turnStatuses[status].length).toBeGreaterThan(0);
    }

    expect(arDict.workspace.banners.rateLimitTitle).toContain("429");
    expect(enDict.workspace.banners.networkErrorTitle).toContain("503");

    for (const country of ["EG", "SA", "AE"] as CountryCode[]) {
      expect(STARTER_PROMPTS[country].length).toBeGreaterThanOrEqual(3);
      for (const prompt of STARTER_PROMPTS[country]) {
        expect(prompt.labelAr.length).toBeGreaterThan(0);
        expect(prompt.labelEn.length).toBeGreaterThan(0);
        expect(prompt.queryAr.length).toBeGreaterThan(0);
        expect(prompt.queryEn.length).toBeGreaterThan(0);
      }
    }

    expect(sanitizeHttpsUrl("https://www.amazon.eg/dp/B0C3ANKEG1")).toBe(
      "https://www.amazon.eg/dp/B0C3ANKEG1",
    );
    expect(sanitizeHttpsUrl("https://www.noon.com/egypt-ar/anker-l4nc/p/?ref=1")).toBe(
      "https://www.noon.com/egypt-ar/anker-l4nc/p/?ref=1",
    );

    expect(sanitizeHttpsUrl("http://www.amazon.eg/dp/B0C3ANKEG1")).toBeNull();
    expect(sanitizeHttpsUrl("javascript:alert(1)")).toBeNull();
    expect(sanitizeHttpsUrl("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(sanitizeHttpsUrl("vbscript:msgbox(1)")).toBeNull();
    expect(sanitizeHttpsUrl("https://user:pass@www.amazon.eg/dp/B0C3ANKEG1")).toBeNull();
    expect(sanitizeHttpsUrl("https://@www.amazon.eg/dp/B0C3ANKEG1")).toBeNull();
    expect(sanitizeHttpsUrl("https://www.amazon.eg\\dp\\1")).toBeNull();
    expect(sanitizeHttpsUrl(" https://www.amazon.eg/dp/1")).toBeNull();
    expect(sanitizeHttpsUrl("https://www.amazon.eg/dp/1\n")).toBeNull();
    expect(sanitizeHttpsUrl(null)).toBeNull();
    expect(sanitizeHttpsUrl("")).toBeNull();
  });

  it("storage isolates EG/SA/AE market sessions and works safely under SSR", () => {
    savePreferences({ country: "SA", store: "noon", language: "en" });
    expect(loadPreferences()).toEqual({ country: "SA", store: "noon", language: "en" });

    const egComparison: ActiveComparisonState = {
      mode: "chat",
      queryLabel: "Anker earbuds",
      rankedOffers: [],
      rankingResult: null,
      sourceMode: "seed",
      cacheHit: false,
      llmCalls: 1,
      latencyMs: 35,
      requestId: "req-eg-1",
      degradedReason: null,
      status: "ok",
      updatedAtIso: "2026-11-16T20:00:00Z",
    };

    const initial = loadMarketSessions();
    initial.EG = {
      sessionId: "sess-eg",
      messages: [
        {
          id: "m1",
          role: "user",
          content: "سماعة أنكر",
          createdAtIso: "2026-11-16T20:00:00Z",
        },
      ],
      activeComparison: egComparison,
    };
    initial.SA = {
      sessionId: "sess-sa",
      messages: [
        {
          id: "m2",
          role: "user",
          content: "قلاية هوائية",
          createdAtIso: "2026-11-16T20:01:00Z",
        },
      ],
      activeComparison: null,
    };
    saveMarketSessions(initial);

    const reloaded = loadMarketSessions();
    expect(reloaded.EG.sessionId).toBe("sess-eg");
    expect(reloaded.SA.sessionId).toBe("sess-sa");
    expect(reloaded.AE.sessionId).toBeNull();

    const afterClear = clearMarketSession("EG");
    expect(afterClear.EG.sessionId).toBeNull();
    expect(afterClear.EG.messages).toEqual([]);
    expect(afterClear.EG.activeComparison).toBeNull();
    expect(afterClear.SA.sessionId).toBe("sess-sa");
    expect(afterClear.SA.messages).toHaveLength(1);

    // SSR mode (window undefined)
    vi.stubGlobal("window", undefined);
    expect(loadPreferences()).toEqual(DEFAULT_USER_PREFERENCES);
    expect(() => savePreferences({ country: "AE", store: "both", language: "ar" })).not.toThrow();
    const ssrSessions = loadMarketSessions();
    expect(ssrSessions.EG.sessionId).toBeNull();
    expect(ssrSessions.SA.sessionId).toBeNull();
    expect(ssrSessions.AE.sessionId).toBeNull();
    expect(() => saveMarketSessions(ssrSessions)).not.toThrow();
    expect(() => clearMarketSession("SA")).not.toThrow();
  });

  it("validateBudgetInput and formatExactPrice reject malformed/out-of-range inputs cleanly", () => {
    expect(validateBudgetInput("")).toEqual({ valid: true, normalized: null, error: null });
    expect(validateBudgetInput("   ")).toEqual({ valid: true, normalized: null, error: null });
    expect(validateBudgetInput("2499.95")).toEqual({
      valid: true,
      normalized: "2499.95",
      error: null,
    });
    expect(validateBudgetInput("10000000")).toEqual({
      valid: true,
      normalized: "10000000.00",
      error: null,
    });

    expect(validateBudgetInput("0")).toEqual({
      valid: false,
      normalized: null,
      error: "non_positive",
    });
    expect(validateBudgetInput("-5")).toEqual({
      valid: false,
      normalized: null,
      error: "non_positive",
    });
    expect(validateBudgetInput("0.001")).toEqual({
      valid: false,
      normalized: null,
      error: "non_positive",
    });
    expect(validateBudgetInput("10000000.01")).toEqual({
      valid: false,
      normalized: null,
      error: "exceeds_max",
    });
    expect(validateBudgetInput("10000000.001")).toEqual({
      valid: false,
      normalized: null,
      error: "exceeds_max",
    });
    expect(validateBudgetInput("1e50")).toEqual({
      valid: false,
      normalized: null,
      error: "invalid_number",
    });
    expect(validateBudgetInput("abc")).toEqual({
      valid: false,
      normalized: null,
      error: "invalid_number",
    });

    expect(formatRatingValue(null, 0, "ar")).toBe("غير مُقيّم");
    expect(formatRatingValue(4.7, 0, "en")).toBe("Unrated");
    expect(formatRatingValue(4.7, 620, "en")).toBe("4.7 / 5 (620 reviews)");
    expect(formatBayesianScore(4.651)).toBe("4.65 / 5.0");
    expect(formatValueScore(88.54)).toBe("88.5 / 100");
    expect(formatLatencyMs(42.3, "en")).toBe("42 ms");
    expect(formatLatencyMs(42.3, "ar")).toBe("42 مللي ثانية");
  });

  it("storage recovers cleanly from corrupted localStorage JSON and invalid schemas", () => {
    window.localStorage.setItem(PREFS_STORAGE_KEY, "{not-valid-json");
    window.localStorage.setItem(MARKET_SESSIONS_STORAGE_KEY, "{broken-sessions");

    expect(loadPreferences()).toEqual(DEFAULT_USER_PREFERENCES);
    const recoveredSessions = loadMarketSessions();
    expect(recoveredSessions.EG).toEqual({ sessionId: null, messages: [], activeComparison: null });
    expect(recoveredSessions.SA).toEqual({ sessionId: null, messages: [], activeComparison: null });
    expect(recoveredSessions.AE).toEqual({ sessionId: null, messages: [], activeComparison: null });

    window.localStorage.setItem(
      PREFS_STORAGE_KEY,
      JSON.stringify({ country: "US", store: "ebay", language: "fr" }),
    );
    window.localStorage.setItem(
      MARKET_SESSIONS_STORAGE_KEY,
      JSON.stringify({ EG: { sessionId: "", messages: ["bad"], activeComparison: { bad: true } } }),
    );

    expect(loadPreferences()).toEqual(DEFAULT_USER_PREFERENCES);
    expect(loadMarketSessions().EG).toEqual({
      sessionId: null,
      messages: [],
      activeComparison: null,
    });
  });
});
