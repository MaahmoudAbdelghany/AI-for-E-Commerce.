"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { fetchHealth, fetchMarkets } from "@/lib/api";
import type {
  ActiveComparisonState,
  BudgetValidationError,
  ChatMessageItem,
  CountryCode,
  DecimalString,
  HealthResponse,
  HealthStatus,
  MarketInfoSchema,
  MarketWorkspaceSession,
  StoreFilter,
  UiLanguage,
} from "@/lib/contracts";
import { validateBudgetInput } from "@/lib/format";
import { getDictionary, type TranslationDictionary } from "@/lib/i18n";
import {
  createEmptyMarketSession,
  createInitialMarketSessions,
  DEFAULT_USER_PREFERENCES,
  loadMarketSessions,
  loadPreferences,
  saveMarketSessions,
  savePreferences,
} from "@/lib/storage";

export const MARKET_REGISTRY_FALLBACK: MarketInfoSchema[] = [
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
];

export interface AppendMarketTurnPayload {
  country?: CountryCode;
  sessionId?: string | null;
  userMessage?: ChatMessageItem;
  assistantMessage?: ChatMessageItem;
  comparison?: ActiveComparisonState | null;
}

export interface ShopSessionContextValue {
  language: UiLanguage;
  setLanguage: (language: UiLanguage) => void;
  country: CountryCode;
  setCountry: (country: CountryCode) => void;
  store: StoreFilter;
  setStore: (store: StoreFilter) => void;
  maxBudget: string;
  setMaxBudget: (value: string) => void;
  parsedMaxBudget: DecimalString | null;
  budgetError: BudgetValidationError | null;
  t: TranslationDictionary;
  markets: MarketInfoSchema[];
  activeMarket: MarketInfoSchema;
  marketsLoading: boolean;
  marketsError: boolean;
  refreshMarkets: (signal?: AbortSignal) => Promise<void>;
  health: HealthResponse | null;
  healthStatus: HealthStatus;
  refreshHealth: (signal?: AbortSignal) => Promise<void>;
  marketSessions: Record<CountryCode, MarketWorkspaceSession>;
  activeMarketSession: MarketWorkspaceSession;
  sessionResetNonce: number;
  appendMarketTurn: (payload: AppendMarketTurnPayload) => void;
  setActiveComparison: (comparison: ActiveComparisonState | null, country?: CountryCode) => void;
  resetActiveMarketSession: () => void;
}

const ShopSessionContext = createContext<ShopSessionContextValue | null>(null);

function syncDocumentLanguageAndDirection(language: UiLanguage): void {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.lang = language;
  document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
}

export function ShopSessionProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<UiLanguage>(DEFAULT_USER_PREFERENCES.language);
  const [country, setCountryState] = useState<CountryCode>(DEFAULT_USER_PREFERENCES.country);
  const [store, setStoreState] = useState<StoreFilter>(DEFAULT_USER_PREFERENCES.store);
  const [maxBudget, setMaxBudget] = useState<string>("");

  const [markets, setMarkets] = useState<MarketInfoSchema[]>(MARKET_REGISTRY_FALLBACK);
  const [marketsLoading, setMarketsLoading] = useState<boolean>(true);
  const [marketsError, setMarketsError] = useState<boolean>(false);

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthStatus, setHealthStatus] = useState<HealthStatus>("checking");

  const [marketSessions, setMarketSessions] = useState<Record<CountryCode, MarketWorkspaceSession>>(
    () => createInitialMarketSessions(),
  );
  const [sessionsHydrated, setSessionsHydrated] = useState<boolean>(false);
  const [sessionResetNonce, setSessionResetNonce] = useState<number>(0);

  const prefsMutatedBeforeHydrationRef = useRef(false);
  const countryRef = useRef<CountryCode>(country);
  const storeRef = useRef<StoreFilter>(store);
  const languageRef = useRef<UiLanguage>(language);
  const healthRequestSeqRef = useRef<number>(0);
  const healthAbortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    countryRef.current = country;
  }, [country]);

  useEffect(() => {
    storeRef.current = store;
  }, [store]);

  useEffect(() => {
    languageRef.current = language;
    syncDocumentLanguageAndDirection(language);
  }, [language]);

  const refreshMarkets = useCallback(async (signal?: AbortSignal) => {
    setMarketsLoading(true);
    try {
      const response = await fetchMarkets(signal);
      if (signal?.aborted) {
        return;
      }
      if (Array.isArray(response.markets) && response.markets.length > 0) {
        setMarkets(response.markets);
        setMarketsError(false);
      } else {
        setMarketsError(true);
      }
    } catch {
      if (signal?.aborted) {
        return;
      }
      setMarketsError(true);
    } finally {
      if (!signal?.aborted) {
        setMarketsLoading(false);
      }
    }
  }, []);

  const refreshHealth = useCallback(async (signal?: AbortSignal) => {
    const requestSeq = healthRequestSeqRef.current + 1;
    healthRequestSeqRef.current = requestSeq;
    healthAbortControllerRef.current?.abort();

    const controller = new AbortController();
    healthAbortControllerRef.current = controller;

    if (signal?.aborted) {
      controller.abort(signal.reason);
      return;
    }

    const onExternalAbort = () => controller.abort(signal?.reason);
    signal?.addEventListener("abort", onExternalAbort, { once: true });

    setHealthStatus("checking");
    try {
      const response = await fetchHealth(controller.signal);
      if (
        requestSeq !== healthRequestSeqRef.current ||
        controller.signal.aborted ||
        signal?.aborted
      ) {
        return;
      }
      setHealth(response);
      setHealthStatus(response.status === "ok" ? "ok" : "degraded");
    } catch {
      if (
        requestSeq !== healthRequestSeqRef.current ||
        controller.signal.aborted ||
        signal?.aborted
      ) {
        return;
      }
      setHealth(null);
      setHealthStatus("offline");
    } finally {
      signal?.removeEventListener("abort", onExternalAbort);
      if (healthAbortControllerRef.current === controller) {
        healthAbortControllerRef.current = null;
      }
    }
  }, []);

  useEffect(() => {
    if (!prefsMutatedBeforeHydrationRef.current) {
      const savedPrefs = loadPreferences();
      countryRef.current = savedPrefs.country;
      storeRef.current = savedPrefs.store;
      languageRef.current = savedPrefs.language;
      setCountryState(savedPrefs.country);
      setStoreState(savedPrefs.store);
      setLanguageState(savedPrefs.language);
      syncDocumentLanguageAndDirection(savedPrefs.language);
    } else {
      syncDocumentLanguageAndDirection(languageRef.current);
    }

    const savedSessions = loadMarketSessions();
    setMarketSessions((prev) => ({
      EG:
        prev.EG.messages.length > 0 || prev.EG.sessionId || prev.EG.activeComparison
          ? prev.EG
          : savedSessions.EG,
      SA:
        prev.SA.messages.length > 0 || prev.SA.sessionId || prev.SA.activeComparison
          ? prev.SA
          : savedSessions.SA,
      AE:
        prev.AE.messages.length > 0 || prev.AE.sessionId || prev.AE.activeComparison
          ? prev.AE
          : savedSessions.AE,
    }));
    setSessionsHydrated(true);

    const controller = new AbortController();
    void refreshMarkets(controller.signal);
    void refreshHealth(controller.signal);
    return () => {
      controller.abort();
      healthAbortControllerRef.current?.abort();
    };
  }, [refreshHealth, refreshMarkets]);

  useEffect(() => {
    if (!sessionsHydrated) {
      return;
    }
    saveMarketSessions(marketSessions);
  }, [marketSessions, sessionsHydrated]);

  const setLanguage = useCallback((nextLanguage: UiLanguage) => {
    prefsMutatedBeforeHydrationRef.current = true;
    languageRef.current = nextLanguage;
    setLanguageState(nextLanguage);
    syncDocumentLanguageAndDirection(nextLanguage);
    savePreferences({
      country: countryRef.current,
      store: storeRef.current,
      language: nextLanguage,
    });
  }, []);

  const setCountry = useCallback((nextCountry: CountryCode) => {
    prefsMutatedBeforeHydrationRef.current = true;
    countryRef.current = nextCountry;
    setCountryState(nextCountry);
    savePreferences({
      country: nextCountry,
      store: storeRef.current,
      language: languageRef.current,
    });
  }, []);

  const setStore = useCallback((nextStore: StoreFilter) => {
    prefsMutatedBeforeHydrationRef.current = true;
    storeRef.current = nextStore;
    setStoreState(nextStore);
    savePreferences({
      country: countryRef.current,
      store: nextStore,
      language: languageRef.current,
    });
  }, []);

  const appendMarketTurn = useCallback((payload: AppendMarketTurnPayload) => {
    const targetCountry = payload.country ?? countryRef.current;
    setMarketSessions((prev) => {
      const existing = prev[targetCountry];
      const nextMessages = [...existing.messages];
      if (payload.userMessage) {
        nextMessages.push(payload.userMessage);
      }
      if (payload.assistantMessage) {
        nextMessages.push(payload.assistantMessage);
      }

      const nextSession: MarketWorkspaceSession = {
        sessionId: payload.sessionId !== undefined ? payload.sessionId : existing.sessionId,
        messages: nextMessages,
        activeComparison:
          payload.comparison !== undefined ? payload.comparison : existing.activeComparison,
      };

      return {
        ...prev,
        [targetCountry]: nextSession,
      };
    });
  }, []);

  const setActiveComparison = useCallback(
    (comparison: ActiveComparisonState | null, targetCountry?: CountryCode) => {
      const resolvedCountry = targetCountry ?? countryRef.current;
      setMarketSessions((prev) => {
        const existing = prev[resolvedCountry];
        return {
          ...prev,
          [resolvedCountry]: {
            ...existing,
            activeComparison: comparison,
          },
        };
      });
    },
    [],
  );

  const resetActiveMarketSession = useCallback(() => {
    const active = countryRef.current;
    setMarketSessions((prev) => ({
      ...prev,
      [active]: createEmptyMarketSession(),
    }));
    setSessionResetNonce((n) => n + 1);
  }, []);

  const budgetValidation = useMemo(() => validateBudgetInput(maxBudget), [maxBudget]);
  const parsedMaxBudget = budgetValidation.valid ? budgetValidation.normalized : null;
  const budgetError = budgetValidation.error;

  const activeMarket = useMemo(() => {
    const found =
      markets.find((item) => item.country === country) ??
      MARKET_REGISTRY_FALLBACK.find((item) => item.country === country) ??
      MARKET_REGISTRY_FALLBACK[0];
    if (!found) {
      throw new Error("Market registry fallback cannot be empty");
    }
    return found;
  }, [markets, country]);

  const t = useMemo(() => getDictionary(language), [language]);
  const activeMarketSession = marketSessions[country];

  const value = useMemo<ShopSessionContextValue>(
    () => ({
      language,
      setLanguage,
      country,
      setCountry,
      store,
      setStore,
      maxBudget,
      setMaxBudget,
      parsedMaxBudget,
      budgetError,
      t,
      markets,
      activeMarket,
      marketsLoading,
      marketsError,
      refreshMarkets,
      health,
      healthStatus,
      refreshHealth,
      marketSessions,
      activeMarketSession,
      sessionResetNonce,
      appendMarketTurn,
      setActiveComparison,
      resetActiveMarketSession,
    }),
    [
      language,
      setLanguage,
      country,
      setCountry,
      store,
      setStore,
      maxBudget,
      parsedMaxBudget,
      budgetError,
      t,
      markets,
      activeMarket,
      marketsLoading,
      marketsError,
      refreshMarkets,
      health,
      healthStatus,
      refreshHealth,
      marketSessions,
      activeMarketSession,
      sessionResetNonce,
      appendMarketTurn,
      setActiveComparison,
      resetActiveMarketSession,
    ],
  );

  return <ShopSessionContext.Provider value={value}>{children}</ShopSessionContext.Provider>;
}

export function useShopSession(): ShopSessionContextValue {
  const ctx = useContext(ShopSessionContext);
  if (!ctx) {
    throw new Error("useShopSession must be used inside a ShopSessionProvider");
  }
  return ctx;
}
