"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useShopSession } from "@/context/ShopSessionContext";
import { ApiClientError, searchOffers, sendChatTurn } from "@/lib/api";
import {
  MAX_SEARCH_QUERY_LENGTH,
  type ActiveComparisonState,
  type ChatMessageItem,
  type ChatResponse,
  type CountryCode,
  type WorkspaceMode,
} from "@/lib/contracts";
import { validateBudgetInput } from "@/lib/format";

import { ChatThread } from "./ChatThread";
import { MessageComposer } from "./MessageComposer";
import { ModeToggle } from "./ModeToggle";
import { ProductComparisonGrid } from "./ProductComparisonGrid";
import { StarterPrompts } from "./StarterPrompts";
import { StatusBanner, type StatusBannerKind } from "./StatusBanner";
import { TelemetryStrip } from "./TelemetryStrip";

type ComposerErrorCode =
  | "query_required"
  | "query_too_long"
  | "query_unsafe_chars"
  | "budget_blocked";

type RetryDescriptor =
  | {
      kind: "chat";
      message: string;
      isCompare: boolean;
      targetCountry: CountryCode;
    }
  | {
      kind: "search";
      query: string;
      minRating: number | null;
      includeAccessories: boolean;
      targetCountry: CountryCode;
    };

interface WorkspaceErrorState {
  kind: "rate_limit" | "network_error" | "generic_error";
  retryAfterSeconds?: number | null;
  message?: string | null;
  retriable: boolean;
  retryDescriptor: RetryDescriptor;
}

function hasControlOrBidiChars(value: string): boolean {
  for (const ch of value) {
    const code = ch.codePointAt(0);
    if (code === undefined) {
      continue;
    }
    if (code < 0x20 || (code >= 0x7f && code <= 0x9f)) {
      return true;
    }
    if (
      (code >= 0x202a && code <= 0x202e) ||
      (code >= 0x2066 && code <= 0x2069) ||
      (code >= 0xe0000 && code <= 0xe007f)
    ) {
      return true;
    }
  }
  return false;
}

function createMessageId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Unified dual-mode RTL-first shopping workspace pairing Conversational Assistant
 * (`/api/v1/chat`) and Zero-LLM Direct Search (`/api/v1/search`) with strictly grounded
 * Top-3 comparison cards, provenance telemetry, market isolation, and safe degradation.
 */
export function ShoppingWorkspace() {
  const {
    language,
    country,
    store,
    maxBudget,
    budgetError,
    activeMarketSession,
    sessionResetNonce,
    appendMarketTurn,
    setActiveComparison,
    t,
  } = useShopSession();

  const [mode, setMode] = useState<WorkspaceMode>("chat");
  const [chatInput, setChatInput] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [minRating, setMinRating] = useState<number | null>(null);
  const [includeAccessories, setIncludeAccessories] = useState<boolean>(false);
  const [composerError, setComposerError] = useState<ComposerErrorCode | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [activeError, setActiveError] = useState<WorkspaceErrorState | null>(null);
  const [turnBannerByCountry, setTurnBannerByCountry] = useState<
    Partial<Record<CountryCode, { kind: StatusBannerKind; retryDescriptor?: RetryDescriptor }>>
  >({});

  const countryRef = useRef<CountryCode>(country);
  const activeSessionRef = useRef(activeMarketSession);
  const requestEpochRef = useRef<number>(0);
  const inFlightRef = useRef<boolean>(false);
  const inFlightControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    countryRef.current = country;
  }, [country]);

  useEffect(() => {
    activeSessionRef.current = activeMarketSession;
  }, [activeMarketSession]);

  // Cancel and ignore in-flight responses on market switch or New Chat reset.
  useEffect(() => {
    requestEpochRef.current += 1;
    inFlightRef.current = false;
    if (inFlightControllerRef.current) {
      inFlightControllerRef.current.abort();
      inFlightControllerRef.current = null;
    }
    setIsSubmitting(false);
    setActiveError(null);
    setComposerError(null);
  }, [country, sessionResetNonce]);

  // Clear per-market turn banner when the active market session is reset via New Chat.
  useEffect(() => {
    if (sessionResetNonce === 0) {
      return;
    }
    setTurnBannerByCountry((prev) => ({
      ...prev,
      [countryRef.current]: undefined,
    }));
  }, [sessionResetNonce]);

  const resolvedComposerError = (() => {
    if (composerError === null) {
      return null;
    }
    if (composerError === "budget_blocked" && budgetError === null) {
      return null;
    }
    switch (composerError) {
      case "query_required":
        return t.workspace.composer.validationQueryRequired;
      case "query_too_long":
        return t.workspace.composer.validationQueryTooLong;
      case "query_unsafe_chars":
        return t.workspace.composer.validationQueryUnsafeChars;
      case "budget_blocked":
        return t.workspace.composer.validationBudgetBlocked;
    }
  })();

  const handleModeChange = useCallback((nextMode: WorkspaceMode) => {
    setMode(nextMode);
    setComposerError(null);
  }, []);

  const validateBudgetBeforeSubmit = useCallback((): {
    ok: boolean;
    normalized: string | null;
  } => {
    const check = validateBudgetInput(maxBudget);
    if (budgetError !== null || !check.valid) {
      setComposerError("budget_blocked");
      return { ok: false, normalized: null };
    }
    return { ok: true, normalized: check.normalized };
  }, [budgetError, maxBudget]);

  const mapChatResponseToTurn = useCallback(
    (
      response: ChatResponse,
      submittedText: string,
      targetCountry: CountryCode,
      isCompare: boolean,
    ) => {
      const nowIso = new Date().toISOString();
      const priorComparison = activeSessionRef.current.activeComparison;
      const isRefused = response.status === "refused";

      const userContent = isRefused ? t.workspace.banners.redactedUserMessage : submittedText;
      const userMessage: ChatMessageItem = {
        id: createMessageId("u"),
        role: "user",
        content: userContent,
        createdAtIso: nowIso,
      };

      const offerCount =
        response.status === "ok"
          ? (response.ranking_result?.ranked_offers.length ?? response.top_offers.length)
          : undefined;

      const assistantMessage: ChatMessageItem = {
        id: createMessageId("a"),
        role: "assistant",
        content: response.reply,
        createdAtIso: nowIso,
        status: response.status,
        action: response.action,
        requestId: response.request_id,
        telemetry: response.telemetry,
        ...(offerCount !== undefined ? { offerCount } : {}),
      };

      let comparisonToSave: ActiveComparisonState | null | undefined;

      if (response.status === "ok") {
        if (response.action === "compare") {
          const nextOffers =
            response.top_offers.length > 0
              ? response.top_offers
              : (priorComparison?.rankedOffers ?? []);
          comparisonToSave = {
            mode: "chat",
            queryLabel:
              response.active_intent?.query ?? priorComparison?.queryLabel ?? submittedText,
            rankedOffers: nextOffers,
            rankingResult: response.ranking_result ?? priorComparison?.rankingResult ?? null,
            sourceMode: response.telemetry.catalog_source_mode,
            cacheHit: response.telemetry.catalog_cache_hit,
            llmCalls: response.telemetry.llm_calls,
            latencyMs: response.telemetry.latency_ms,
            requestId: response.request_id,
            degradedReason: response.telemetry.degraded_reason,
            status: response.status,
            updatedAtIso: nowIso,
          };
        } else {
          const nextOffers = response.ranking_result?.ranked_offers ?? response.top_offers;
          comparisonToSave = {
            mode: "chat",
            queryLabel: response.active_intent?.query ?? submittedText,
            rankedOffers: nextOffers,
            rankingResult: response.ranking_result,
            sourceMode: response.telemetry.catalog_source_mode,
            cacheHit: response.telemetry.catalog_cache_hit,
            llmCalls: response.telemetry.llm_calls,
            latencyMs: response.telemetry.latency_ms,
            requestId: response.request_id,
            degradedReason: response.telemetry.degraded_reason,
            status: response.status,
            updatedAtIso: nowIso,
          };
        }

        setTurnBannerByCountry((prev) => ({ ...prev, [targetCountry]: undefined }));
      } else if (response.status === "degraded") {
        comparisonToSave = null;
        setTurnBannerByCountry((prev) => ({
          ...prev,
          [targetCountry]: {
            kind: "degraded",
            retryDescriptor: {
              kind: "chat",
              message: submittedText,
              isCompare,
              targetCountry,
            },
          },
        }));
      } else {
        // clarify, off_topic, refused: preserve prior valid ActiveComparisonState intact.
        comparisonToSave = undefined;
        setTurnBannerByCountry((prev) => ({
          ...prev,
          [targetCountry]: {
            kind: response.status,
          },
        }));
      }

      appendMarketTurn({
        country: targetCountry,
        sessionId: response.session_id,
        userMessage,
        assistantMessage,
        ...(comparisonToSave !== undefined ? { comparison: comparisonToSave } : {}),
      });
    },
    [appendMarketTurn, t.workspace.banners.redactedUserMessage],
  );

  const mapApiError = useCallback((err: unknown, retryDescriptor: RetryDescriptor): WorkspaceErrorState => {
    if (err instanceof ApiClientError) {
      if (err.status === 429) {
        return {
          kind: "rate_limit",
          retryAfterSeconds: err.retryAfterSeconds,
          retriable: true,
          retryDescriptor,
        };
      }
      if (err.status === 503 || err.status === 0 || err.errorCode === "backend_unreachable") {
        return {
          kind: "network_error",
          retriable: true,
          retryDescriptor,
        };
      }
      return {
        kind: "generic_error",
        message: err.message,
        retriable: err.retriable,
        retryDescriptor,
      };
    }

    return {
      kind: "network_error",
      retriable: true,
      retryDescriptor,
    };
  }, []);

  const executeChatTurn = useCallback(
    async (
      rawMessage: string,
      options: { clearComposer?: boolean; isCompare?: boolean } = {},
    ) => {
      if (inFlightRef.current) {
        return;
      }

      const trimmed = rawMessage.trim();
      if (!trimmed) {
        setComposerError("query_required");
        return;
      }

      const budgetCheck = validateBudgetBeforeSubmit();
      if (!budgetCheck.ok) {
        return;
      }

      const targetCountry = countryRef.current;
      const sessionSnapshot = activeSessionRef.current;
      const requestEpoch = requestEpochRef.current + 1;
      requestEpochRef.current = requestEpoch;

      const controller = new AbortController();
      inFlightControllerRef.current = controller;
      inFlightRef.current = true;
      setIsSubmitting(true);
      setComposerError(null);
      setActiveError(null);

      try {
        const response = await sendChatTurn(
          {
            message: trimmed,
            session_id: sessionSnapshot.sessionId,
            country: targetCountry,
            store,
            ...(budgetCheck.normalized !== null ? { max_budget: budgetCheck.normalized } : {}),
            language,
          },
          controller.signal,
        );

        if (requestEpoch !== requestEpochRef.current || targetCountry !== countryRef.current) {
          return;
        }

        if (options.clearComposer || response.status === "refused") {
          setChatInput("");
        }

        mapChatResponseToTurn(response, trimmed, targetCountry, Boolean(options.isCompare));
      } catch (err) {
        if (requestEpoch !== requestEpochRef.current || targetCountry !== countryRef.current) {
          return;
        }
        setActiveError(
          mapApiError(err, {
            kind: "chat",
            message: trimmed,
            isCompare: Boolean(options.isCompare),
            targetCountry,
          }),
        );
      } finally {
        if (requestEpoch === requestEpochRef.current) {
          inFlightRef.current = false;
          inFlightControllerRef.current = null;
          setIsSubmitting(false);
        }
      }
    },
    [language, mapApiError, mapChatResponseToTurn, store, validateBudgetBeforeSubmit],
  );

  const executeDirectSearch = useCallback(
    async (
      rawQuery: string,
      searchMinRating: number | null,
      searchIncludeAccessories: boolean,
    ) => {
      if (inFlightRef.current) {
        return;
      }

      if (hasControlOrBidiChars(rawQuery)) {
        setComposerError("query_unsafe_chars");
        return;
      }

      const trimmed = rawQuery.trim();
      if (!trimmed) {
        setComposerError("query_required");
        return;
      }
      if (rawQuery.length > MAX_SEARCH_QUERY_LENGTH || trimmed.length > MAX_SEARCH_QUERY_LENGTH) {
        setComposerError("query_too_long");
        return;
      }

      const budgetCheck = validateBudgetBeforeSubmit();
      if (!budgetCheck.ok) {
        return;
      }

      const targetCountry = countryRef.current;
      const requestEpoch = requestEpochRef.current + 1;
      requestEpochRef.current = requestEpoch;

      const controller = new AbortController();
      inFlightControllerRef.current = controller;
      inFlightRef.current = true;
      setIsSubmitting(true);
      setComposerError(null);
      setActiveError(null);

      try {
        const response = await searchOffers(
          {
            query: trimmed,
            country: targetCountry,
            store,
            ...(budgetCheck.normalized !== null ? { max_budget: budgetCheck.normalized } : {}),
            ...(searchMinRating !== null ? { min_rating: searchMinRating } : {}),
            include_accessories: searchIncludeAccessories,
            language,
          },
          controller.signal,
        );

        if (requestEpoch !== requestEpochRef.current || targetCountry !== countryRef.current) {
          return;
        }

        const nextComparison: ActiveComparisonState = {
          mode: "search",
          queryLabel: response.intent.query,
          rankedOffers: response.ranking_result.ranked_offers,
          rankingResult: response.ranking_result,
          sourceMode: response.source_mode,
          cacheHit: response.cache_hit,
          llmCalls: 0,
          latencyMs: response.latency_ms,
          requestId: response.request_id,
          degradedReason: null,
          status: "search_ok",
          updatedAtIso: new Date().toISOString(),
        };

        setTurnBannerByCountry((prev) => ({ ...prev, [targetCountry]: undefined }));
        setActiveComparison(nextComparison, targetCountry);
      } catch (err) {
        if (requestEpoch !== requestEpochRef.current || targetCountry !== countryRef.current) {
          return;
        }
        setActiveError(
          mapApiError(err, {
            kind: "search",
            query: rawQuery,
            minRating: searchMinRating,
            includeAccessories: searchIncludeAccessories,
            targetCountry,
          }),
        );
      } finally {
        if (requestEpoch === requestEpochRef.current) {
          inFlightRef.current = false;
          inFlightControllerRef.current = null;
          setIsSubmitting(false);
        }
      }
    },
    [language, mapApiError, setActiveComparison, store, validateBudgetBeforeSubmit],
  );

  const handleRetryDescriptor = useCallback(
    (descriptor: RetryDescriptor) => {
      if (descriptor.targetCountry !== countryRef.current || inFlightRef.current) {
        return;
      }
      if (descriptor.kind === "chat") {
        void executeChatTurn(descriptor.message, {
          clearComposer: false,
          isCompare: descriptor.isCompare,
        });
      } else {
        void executeDirectSearch(
          descriptor.query,
          descriptor.minRating,
          descriptor.includeAccessories,
        );
      }
    },
    [executeChatTurn, executeDirectSearch],
  );

  const activeComparison = activeMarketSession.activeComparison;
  const activeOffers = activeComparison?.rankedOffers ?? [];
  const canCompareSaved = activeOffers.length >= 2;
  const activeTurnBanner = turnBannerByCountry[country];

  const showPartialBanner =
    activeComparison !== null &&
    activeOffers.length > 0 &&
    activeOffers.length < 3 &&
    activeComparison.rankingResult?.degraded_fewer_than_k === true;

  const showNoResultsBanner = activeComparison !== null && activeOffers.length === 0;

  return (
    <div className="grid min-w-0 grid-cols-1 gap-6 lg:grid-cols-12 lg:items-start">
      <section
        aria-label={t.workspace.modeToggleLabel}
        className="min-w-0 space-y-4 lg:col-span-5"
      >
        <ModeToggle mode={mode} onModeChange={handleModeChange} disabled={isSubmitting} t={t} />

        {activeComparison !== null && (
          <div className="lg:hidden">
            <a
              href="#comparison-panel"
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-teal-700 bg-teal-50 px-3 py-2 text-xs font-semibold text-teal-900 transition-colors hover:bg-teal-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
            >
              <span>{t.workspace.mobileQuickJump.label}</span>
              {activeOffers.length > 0 && (
                <span className="rounded-full bg-teal-700 px-2 py-0.5 text-[11px] font-bold text-white">
                  {activeOffers.length}
                </span>
              )}
            </a>
          </div>
        )}

        {activeError ? (
          <StatusBanner
            kind={activeError.kind}
            t={t}
            retryAfterSeconds={activeError.retryAfterSeconds ?? null}
            detailMessage={activeError.message ?? null}
            onRetry={
              activeError.retriable
                ? () => handleRetryDescriptor(activeError.retryDescriptor)
                : undefined
            }
            isRetrying={isSubmitting}
          />
        ) : (
          activeTurnBanner && (
            <StatusBanner
              kind={activeTurnBanner.kind}
              t={t}
              onRetry={
                activeTurnBanner.retryDescriptor
                  ? () => handleRetryDescriptor(activeTurnBanner.retryDescriptor!)
                  : undefined
              }
              isRetrying={isSubmitting}
            />
          )
        )}

        {mode === "chat" && (
          <>
            <StarterPrompts
              country={country}
              language={language}
              disabled={isSubmitting}
              onSelectPrompt={(queryText) => {
                void executeChatTurn(queryText, { clearComposer: false });
              }}
              t={t}
            />
            <ChatThread
              messages={activeMarketSession.messages}
              isLoading={isSubmitting}
              t={t}
            />
          </>
        )}

        <MessageComposer
          mode={mode}
          chatInput={chatInput}
          onChatInputChange={(val) => {
            setChatInput(val);
            if (composerError !== null && composerError !== "budget_blocked") {
              setComposerError(null);
            }
          }}
          searchQuery={searchQuery}
          onSearchQueryChange={(val) => {
            setSearchQuery(val);
            if (composerError !== null && composerError !== "budget_blocked") {
              setComposerError(null);
            }
          }}
          minRating={minRating}
          onMinRatingChange={setMinRating}
          includeAccessories={includeAccessories}
          onIncludeAccessoriesChange={setIncludeAccessories}
          isSubmitting={isSubmitting}
          canCompareSaved={canCompareSaved}
          validationError={resolvedComposerError}
          onSubmitChat={() => {
            void executeChatTurn(chatInput, { clearComposer: true });
          }}
          onSubmitSearch={() => {
            void executeDirectSearch(searchQuery, minRating, includeAccessories);
          }}
          onCompareSaved={() => {
            void executeChatTurn(t.workspace.composer.compareSavedDefaultQuery, {
              clearComposer: false,
              isCompare: true,
            });
          }}
          t={t}
        />
      </section>

      <section
        id="comparison-panel"
        aria-label={t.workspace.comparison.panelTitle}
        className="min-w-0 space-y-4 lg:sticky lg:top-4 lg:col-span-7"
      >
        {activeComparison && (
          <TelemetryStrip
            sourceMode={activeComparison.sourceMode}
            cacheHit={activeComparison.cacheHit}
            llmCalls={activeComparison.llmCalls}
            latencyMs={activeComparison.latencyMs}
            requestId={activeComparison.requestId}
            rankingResult={activeComparison.rankingResult}
            language={language}
            t={t}
          />
        )}

        {showPartialBanner && <StatusBanner kind="partial" t={t} />}
        {showNoResultsBanner && <StatusBanner kind="no_results" t={t} />}

        <ProductComparisonGrid
          rankedOffers={activeOffers}
          language={language}
          t={t}
          queryLabel={activeComparison?.queryLabel}
          hasActiveComparison={activeComparison !== null}
        />
      </section>
    </div>
  );
}
