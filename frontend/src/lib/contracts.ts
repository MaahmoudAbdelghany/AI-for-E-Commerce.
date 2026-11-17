/**
 * Strict TypeScript DTO contracts mirroring `backend/src/commerce_ai/api/schemas.py`
 * and `backend/src/commerce_ai/domain/models.py`, plus pre-defined Phase 3 UI types.
 */

export const MAX_BUDGET_LIMIT = 10_000_000;
export const MAX_SEARCH_QUERY_LENGTH = 500;

export const SUPPORTED_COUNTRIES = ["EG", "SA", "AE"] as const;
export const SUPPORTED_STORE_FILTERS = ["both", "noon", "amazon"] as const;

export type CountryCode = "EG" | "SA" | "AE";
export type CurrencyCode = "EGP" | "SAR" | "AED";
export type StoreId = "noon" | "amazon";
export type StoreFilter = "noon" | "amazon" | "both";
export type CatalogSourceMode = "seed" | "live";
export type TurnAction = "search" | "compare" | "clarify" | "off_topic" | "refuse";
export type TurnStatus = "ok" | "clarify" | "off_topic" | "refused" | "degraded";
export type UiLanguage = "ar" | "en";

export type MatchReasonCode =
  | "best_overall_value"
  | "lowest_price"
  | "top_bayesian_rating"
  | "high_review_confidence"
  | "within_budget"
  | "unrated_fallback"
  | "strong_value_runner_up";

/** Decimal string serialized verbatim from backend `Decimal` fields (no IEEE-754 rounding). */
export type DecimalString = string;

export interface ProductOffer {
  offer_id: string;
  title: string;
  price: DecimalString;
  currency: CurrencyCode;
  store: StoreId;
  country: CountryCode;
  url: string;
  rating: number | null;
  review_count: number;
  image_url: string | null;
  in_stock: boolean;
}

export interface SearchIntent {
  query: string;
  country: CountryCode;
  store: StoreFilter;
  max_budget: DecimalString | null;
  min_rating: number | null;
  exclude_keywords: string[];
  include_accessories: boolean;
  language: UiLanguage;
}

export interface RankedOffer {
  rank: number;
  offer: ProductOffer;
  value_score: number;
  price_norm: number;
  bayesian_rating: number;
  match_reasons: string[];
}

export interface RankingResult {
  ranked_offers: RankedOffer[];
  total_candidates: number;
  filtered_accessories_count: number;
  filtered_outliers_count: number;
  degraded_fewer_than_k: boolean;
}

export interface TurnTelemetry {
  llm_calls: number;
  catalog_called: boolean;
  catalog_cache_hit: boolean;
  catalog_source_mode: CatalogSourceMode | null;
  used_rule_intent_fallback: boolean;
  used_template_summary: boolean;
  degraded_reason: string | null;
  latency_ms: number;
}

export interface ChatRequest {
  message: string;
  session_id?: string | null;
  country?: CountryCode;
  store?: StoreFilter | null;
  max_budget?: string | number | null;
  language?: UiLanguage | null;
}

export interface ChatResponse {
  session_id: string;
  status: TurnStatus;
  reply: string;
  action: TurnAction;
  active_intent: SearchIntent | null;
  top_offers: RankedOffer[];
  ranking_result: RankingResult | null;
  telemetry: TurnTelemetry;
  request_id: string;
}

export interface SearchRequest {
  query: string;
  country?: CountryCode;
  store?: StoreFilter;
  max_budget?: string | number | null;
  min_rating?: number | null;
  include_accessories?: boolean;
  language?: UiLanguage;
}

export interface SearchResponse {
  intent: SearchIntent;
  ranking_result: RankingResult;
  source_mode: CatalogSourceMode;
  cache_hit: boolean;
  latency_ms: number;
  request_id: string;
}

export interface MarketStoreSchema {
  store_id: StoreId;
  label_en: string;
  label_ar: string;
  primary_domain: string;
}

export interface MarketInfoSchema {
  country: CountryCode;
  currency: CurrencyCode;
  name_en: string;
  name_ar: string;
  currency_label_en: string;
  currency_label_ar: string;
  serper_gl: string;
  stores: MarketStoreSchema[];
}

export interface MarketsResponse {
  markets: MarketInfoSchema[];
  default_country: CountryCode;
  default_store: StoreFilter;
  request_id: string;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  app_env: string;
  catalog_mode: string;
  llm_mode: string;
  cache_backend: string;
  session_backend: string;
  version: string;
}

export interface ErrorResponse {
  error_code: string;
  message: string;
  retriable: boolean;
  request_id: string;
  details: Array<Record<string, unknown>> | null;
}

export type WorkspaceMode = "chat" | "search";
export type BudgetValidationError = "invalid_number" | "non_positive" | "exceeds_max";
export type HealthStatus = "checking" | "ok" | "degraded" | "offline";

export interface ChatMessageItem {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAtIso: string;
  status?: TurnStatus;
  action?: TurnAction;
  requestId?: string;
  telemetry?: TurnTelemetry;
  offerCount?: number;
}

export interface ActiveComparisonState {
  mode: WorkspaceMode;
  queryLabel: string;
  rankedOffers: RankedOffer[];
  rankingResult: RankingResult | null;
  sourceMode: CatalogSourceMode | null;
  cacheHit: boolean;
  llmCalls: number;
  latencyMs: number;
  requestId: string;
  degradedReason: string | null;
  status: TurnStatus | "search_ok";
  updatedAtIso: string;
}

export interface MarketWorkspaceSession {
  sessionId: string | null;
  messages: ChatMessageItem[];
  activeComparison: ActiveComparisonState | null;
}

export interface UserPreferences {
  country: CountryCode;
  store: StoreFilter;
  language: UiLanguage;
}
