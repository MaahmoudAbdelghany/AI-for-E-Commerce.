import type {
  ActiveComparisonState,
  ChatMessageItem,
  CountryCode,
  MarketWorkspaceSession,
  StoreFilter,
  UiLanguage,
  UserPreferences,
} from "@/lib/contracts";

export const PREFS_STORAGE_KEY = "commerce_ai.prefs.v1";
export const MARKET_SESSIONS_STORAGE_KEY = "commerce_ai.market_sessions.v1";

export const DEFAULT_USER_PREFERENCES: UserPreferences = {
  country: "EG",
  store: "both",
  language: "ar",
};

const VALID_COUNTRIES = new Set<CountryCode>(["EG", "SA", "AE"]);
const VALID_STORES = new Set<StoreFilter>(["both", "noon", "amazon"]);
const VALID_LANGUAGES = new Set<UiLanguage>(["ar", "en"]);
const VALID_STATUSES = new Set(["ok", "clarify", "off_topic", "refused", "degraded", "search_ok"]);
const VALID_ACTIONS = new Set(["search", "compare", "clarify", "off_topic", "refuse"]);

function getSafeStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function createEmptyMarketSession(): MarketWorkspaceSession {
  return {
    sessionId: null,
    messages: [],
    activeComparison: null,
  };
}

export function createInitialMarketSessions(): Record<CountryCode, MarketWorkspaceSession> {
  return {
    EG: createEmptyMarketSession(),
    SA: createEmptyMarketSession(),
    AE: createEmptyMarketSession(),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sanitizeMessages(raw: unknown): ChatMessageItem[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const result: ChatMessageItem[] = [];
  for (const item of raw) {
    if (!isRecord(item)) {
      continue;
    }
    if (
      typeof item.id !== "string" ||
      (item.role !== "user" && item.role !== "assistant") ||
      typeof item.content !== "string" ||
      typeof item.createdAtIso !== "string"
    ) {
      continue;
    }
    const sanitized: ChatMessageItem = {
      id: item.id,
      role: item.role,
      content: item.content,
      createdAtIso: item.createdAtIso,
    };
    if (typeof item.status === "string" && VALID_STATUSES.has(item.status) && item.status !== "search_ok") {
      sanitized.status = item.status as ChatMessageItem["status"];
    }
    if (typeof item.action === "string" && VALID_ACTIONS.has(item.action)) {
      sanitized.action = item.action as ChatMessageItem["action"];
    }
    if (typeof item.requestId === "string") {
      sanitized.requestId = item.requestId;
    }
    if (isRecord(item.telemetry)) {
      sanitized.telemetry = item.telemetry as unknown as ChatMessageItem["telemetry"];
    }
    if (typeof item.offerCount === "number" && Number.isFinite(item.offerCount)) {
      sanitized.offerCount = item.offerCount;
    }
    result.push(sanitized);
  }
  return result;
}

function sanitizeActiveComparison(raw: unknown): ActiveComparisonState | null {
  if (!isRecord(raw)) {
    return null;
  }
  if (
    (raw.mode !== "chat" && raw.mode !== "search") ||
    typeof raw.queryLabel !== "string" ||
    !Array.isArray(raw.rankedOffers) ||
    typeof raw.cacheHit !== "boolean" ||
    typeof raw.llmCalls !== "number" ||
    typeof raw.latencyMs !== "number" ||
    typeof raw.requestId !== "string" ||
    typeof raw.status !== "string" ||
    !VALID_STATUSES.has(raw.status) ||
    typeof raw.updatedAtIso !== "string"
  ) {
    return null;
  }

  return {
    mode: raw.mode,
    queryLabel: raw.queryLabel,
    rankedOffers: raw.rankedOffers as ActiveComparisonState["rankedOffers"],
    rankingResult: isRecord(raw.rankingResult)
      ? (raw.rankingResult as unknown as ActiveComparisonState["rankingResult"])
      : null,
    sourceMode: raw.sourceMode === "seed" || raw.sourceMode === "live" ? raw.sourceMode : null,
    cacheHit: raw.cacheHit,
    llmCalls: raw.llmCalls,
    latencyMs: raw.latencyMs,
    requestId: raw.requestId,
    degradedReason: typeof raw.degradedReason === "string" ? raw.degradedReason : null,
    status: raw.status as ActiveComparisonState["status"],
    updatedAtIso: raw.updatedAtIso,
  };
}

function sanitizeMarketSession(raw: unknown): MarketWorkspaceSession {
  if (!isRecord(raw)) {
    return createEmptyMarketSession();
  }
  const sessionId =
    typeof raw.sessionId === "string" && raw.sessionId.trim().length > 0 ? raw.sessionId.trim() : null;
  return {
    sessionId,
    messages: sanitizeMessages(raw.messages),
    activeComparison: sanitizeActiveComparison(raw.activeComparison),
  };
}

export function loadPreferences(): UserPreferences {
  const storage = getSafeStorage();
  if (!storage) {
    return { ...DEFAULT_USER_PREFERENCES };
  }

  try {
    const raw = storage.getItem(PREFS_STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_USER_PREFERENCES };
    }
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) {
      return { ...DEFAULT_USER_PREFERENCES };
    }

    const country = VALID_COUNTRIES.has(parsed.country as CountryCode)
      ? (parsed.country as CountryCode)
      : DEFAULT_USER_PREFERENCES.country;
    const store = VALID_STORES.has(parsed.store as StoreFilter)
      ? (parsed.store as StoreFilter)
      : DEFAULT_USER_PREFERENCES.store;
    const language = VALID_LANGUAGES.has(parsed.language as UiLanguage)
      ? (parsed.language as UiLanguage)
      : DEFAULT_USER_PREFERENCES.language;

    return { country, store, language };
  } catch {
    return { ...DEFAULT_USER_PREFERENCES };
  }
}

export function savePreferences(prefs: UserPreferences): void {
  const storage = getSafeStorage();
  if (!storage) {
    return;
  }
  try {
    storage.setItem(PREFS_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Ignore storage quota or privacy-mode errors cleanly.
  }
}

export function loadMarketSessions(): Record<CountryCode, MarketWorkspaceSession> {
  const fallback = createInitialMarketSessions();
  const storage = getSafeStorage();
  if (!storage) {
    return fallback;
  }

  try {
    const raw = storage.getItem(MARKET_SESSIONS_STORAGE_KEY);
    if (!raw) {
      return fallback;
    }
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) {
      return fallback;
    }

    return {
      EG: sanitizeMarketSession(parsed.EG),
      SA: sanitizeMarketSession(parsed.SA),
      AE: sanitizeMarketSession(parsed.AE),
    };
  } catch {
    return fallback;
  }
}

export function saveMarketSessions(sessions: Record<CountryCode, MarketWorkspaceSession>): void {
  const storage = getSafeStorage();
  if (!storage) {
    return;
  }
  try {
    storage.setItem(MARKET_SESSIONS_STORAGE_KEY, JSON.stringify(sessions));
  } catch {
    // Ignore storage quota or privacy-mode errors cleanly.
  }
}

export function clearMarketSession(country: CountryCode): Record<CountryCode, MarketWorkspaceSession> {
  const current = loadMarketSessions();
  const updated: Record<CountryCode, MarketWorkspaceSession> = {
    ...current,
    [country]: createEmptyMarketSession(),
  };
  saveMarketSessions(updated);
  return updated;
}
