import type {
  ActiveComparisonState,
  CatalogSourceMode,
  ChatMessageItem,
  CountryCode,
  CurrencyCode,
  MarketWorkspaceSession,
  ProductOffer,
  RankedOffer,
  RankingResult,
  StoreFilter,
  StoreId,
  TurnTelemetry,
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
const VALID_CURRENCIES = new Set<CurrencyCode>(["EGP", "SAR", "AED"]);
const VALID_STORE_IDS = new Set<StoreId>(["noon", "amazon"]);
const VALID_STORES = new Set<StoreFilter>(["both", "noon", "amazon"]);
const VALID_LANGUAGES = new Set<UiLanguage>(["ar", "en"]);
const VALID_STATUSES = new Set(["ok", "clarify", "off_topic", "refused", "degraded", "search_ok"]);
const VALID_ACTIONS = new Set(["search", "compare", "clarify", "off_topic", "refuse"]);
const VALID_SOURCE_MODES = new Set<CatalogSourceMode>(["seed", "live"]);

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

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function sanitizeProductOffer(raw: unknown): ProductOffer | null {
  if (!isRecord(raw)) {
    return null;
  }
  if (
    typeof raw.offer_id !== "string" ||
    raw.offer_id.length === 0 ||
    typeof raw.title !== "string" ||
    typeof raw.price !== "string" ||
    raw.price.trim().length === 0 ||
    typeof raw.currency !== "string" ||
    !VALID_CURRENCIES.has(raw.currency as CurrencyCode) ||
    typeof raw.store !== "string" ||
    !VALID_STORE_IDS.has(raw.store as StoreId) ||
    typeof raw.country !== "string" ||
    !VALID_COUNTRIES.has(raw.country as CountryCode) ||
    typeof raw.url !== "string" ||
    (raw.rating !== null && !isFiniteNumber(raw.rating)) ||
    !isFiniteNumber(raw.review_count) ||
    raw.review_count < 0 ||
    (raw.image_url !== null && typeof raw.image_url !== "string") ||
    typeof raw.in_stock !== "boolean"
  ) {
    return null;
  }

  return {
    offer_id: raw.offer_id,
    title: raw.title,
    price: raw.price,
    currency: raw.currency as CurrencyCode,
    store: raw.store as StoreId,
    country: raw.country as CountryCode,
    url: raw.url,
    rating: raw.rating,
    review_count: raw.review_count,
    image_url: raw.image_url,
    in_stock: raw.in_stock,
  };
}

function sanitizeRankedOffer(raw: unknown): RankedOffer | null {
  if (!isRecord(raw)) {
    return null;
  }
  const offer = sanitizeProductOffer(raw.offer);
  if (
    !offer ||
    !isFiniteNumber(raw.rank) ||
    !isFiniteNumber(raw.value_score) ||
    !isFiniteNumber(raw.price_norm) ||
    !isFiniteNumber(raw.bayesian_rating) ||
    !Array.isArray(raw.match_reasons) ||
    !raw.match_reasons.every((reason) => typeof reason === "string")
  ) {
    return null;
  }

  return {
    rank: raw.rank,
    offer,
    value_score: raw.value_score,
    price_norm: raw.price_norm,
    bayesian_rating: raw.bayesian_rating,
    match_reasons: [...raw.match_reasons],
  };
}

function sanitizeRankedOffersArray(raw: unknown): RankedOffer[] | null {
  if (!Array.isArray(raw)) {
    return null;
  }
  const result: RankedOffer[] = [];
  for (const item of raw) {
    const sanitized = sanitizeRankedOffer(item);
    if (!sanitized) {
      return null;
    }
    result.push(sanitized);
  }
  return result;
}

function sanitizeRankingResult(raw: unknown): RankingResult | null {
  if (!isRecord(raw)) {
    return null;
  }
  const rankedOffers = sanitizeRankedOffersArray(raw.ranked_offers);
  if (
    !rankedOffers ||
    !isFiniteNumber(raw.total_candidates) ||
    !isFiniteNumber(raw.filtered_accessories_count) ||
    !isFiniteNumber(raw.filtered_outliers_count) ||
    typeof raw.degraded_fewer_than_k !== "boolean"
  ) {
    return null;
  }

  return {
    ranked_offers: rankedOffers,
    total_candidates: raw.total_candidates,
    filtered_accessories_count: raw.filtered_accessories_count,
    filtered_outliers_count: raw.filtered_outliers_count,
    degraded_fewer_than_k: raw.degraded_fewer_than_k,
  };
}

function sanitizeTurnTelemetry(raw: unknown): TurnTelemetry | null {
  if (!isRecord(raw)) {
    return null;
  }
  const sourceMode = raw.catalog_source_mode;
  const validSourceMode =
    sourceMode === null ||
    (typeof sourceMode === "string" && VALID_SOURCE_MODES.has(sourceMode as CatalogSourceMode));
  if (
    !isFiniteNumber(raw.llm_calls) ||
    typeof raw.catalog_called !== "boolean" ||
    typeof raw.catalog_cache_hit !== "boolean" ||
    !validSourceMode ||
    typeof raw.used_rule_intent_fallback !== "boolean" ||
    typeof raw.used_template_summary !== "boolean" ||
    (raw.degraded_reason !== null && typeof raw.degraded_reason !== "string") ||
    !isFiniteNumber(raw.latency_ms)
  ) {
    return null;
  }

  return {
    llm_calls: raw.llm_calls,
    catalog_called: raw.catalog_called,
    catalog_cache_hit: raw.catalog_cache_hit,
    catalog_source_mode: sourceMode as CatalogSourceMode | null,
    used_rule_intent_fallback: raw.used_rule_intent_fallback,
    used_template_summary: raw.used_template_summary,
    degraded_reason: raw.degraded_reason,
    latency_ms: raw.latency_ms,
  };
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
    if (item.telemetry !== undefined) {
      const sanitizedTelemetry = sanitizeTurnTelemetry(item.telemetry);
      if (sanitizedTelemetry) {
        sanitized.telemetry = sanitizedTelemetry;
      }
    }
    if (isFiniteNumber(item.offerCount)) {
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
  const rankedOffers = sanitizeRankedOffersArray(raw.rankedOffers);
  if (
    (raw.mode !== "chat" && raw.mode !== "search") ||
    typeof raw.queryLabel !== "string" ||
    !rankedOffers ||
    typeof raw.cacheHit !== "boolean" ||
    !isFiniteNumber(raw.llmCalls) ||
    !isFiniteNumber(raw.latencyMs) ||
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
    rankedOffers,
    rankingResult:
      raw.rankingResult !== null && raw.rankingResult !== undefined
        ? sanitizeRankingResult(raw.rankingResult)
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
