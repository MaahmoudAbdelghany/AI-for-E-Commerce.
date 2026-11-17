"use client";

import type { TranslationDictionary } from "@/lib/i18n";

export type StatusBannerKind =
  | "clarify"
  | "off_topic"
  | "refused"
  | "degraded"
  | "partial"
  | "no_results"
  | "rate_limit"
  | "network_error"
  | "generic_error";

export interface StatusBannerProps {
  kind: StatusBannerKind;
  t: TranslationDictionary;
  retryAfterSeconds?: number | null;
  detailMessage?: string | null;
  onRetry?: () => void;
  isRetrying?: boolean;
}

const BANNER_STYLES: Record<StatusBannerKind, string> = {
  clarify: "border-sky-200 bg-sky-50 text-sky-950",
  off_topic: "border-slate-300 bg-slate-100 text-slate-900",
  refused: "border-rose-300 bg-rose-50 text-rose-950",
  degraded: "border-amber-300 bg-amber-50 text-amber-950",
  partial: "border-amber-200 bg-amber-50 text-amber-950",
  no_results: "border-slate-300 bg-slate-50 text-slate-900",
  rate_limit: "border-amber-300 bg-amber-50 text-amber-950",
  network_error: "border-rose-300 bg-rose-50 text-rose-950",
  generic_error: "border-rose-300 bg-rose-50 text-rose-950",
};

const ALERT_KINDS = new Set<StatusBannerKind>([
  "refused",
  "degraded",
  "rate_limit",
  "network_error",
  "generic_error",
]);

/**
 * Accessible bilingual degradation, guardrail, and error banner (`INV-08`, `INV-09`).
 * Never echoes raw user input when `kind === "refused"`.
 */
export function StatusBanner({
  kind,
  t,
  retryAfterSeconds = null,
  detailMessage = null,
  onRetry,
  isRetrying = false,
}: StatusBannerProps) {
  const role = ALERT_KINDS.has(kind) ? "alert" : "status";
  const styleClass = BANNER_STYLES[kind];

  let title = "";
  let body = "";

  switch (kind) {
    case "clarify":
      title = t.workspace.banners.clarifyTitle;
      body = detailMessage || t.workspace.banners.clarifyHint;
      break;
    case "off_topic":
      title = t.workspace.banners.offTopicTitle;
      body = t.workspace.banners.offTopicHint;
      break;
    case "refused":
      // INV-09: strictly ignore detailMessage so sensitive user text is never echoed.
      title = t.workspace.banners.refusedTitle;
      body = t.workspace.banners.refusedHint;
      break;
    case "degraded":
      title = t.workspace.banners.degradedTitle;
      body = t.workspace.banners.degradedHint;
      break;
    case "partial":
      title = t.workspace.banners.partialResultsTitle;
      body = t.workspace.banners.partialResultsHint;
      break;
    case "no_results":
      title = t.workspace.banners.noResultsTitle;
      body = t.workspace.banners.noResultsHint;
      break;
    case "rate_limit":
      title = t.workspace.banners.rateLimitTitle;
      body =
        retryAfterSeconds !== null && Number.isFinite(retryAfterSeconds)
          ? t.workspace.banners.rateLimitWithSeconds.replace(
              "{seconds}",
              String(retryAfterSeconds),
            )
          : t.workspace.banners.rateLimitGeneric;
      break;
    case "network_error":
      title = t.workspace.banners.networkErrorTitle;
      body = t.workspace.banners.networkErrorBody;
      break;
    case "generic_error":
      title = t.workspace.banners.networkErrorTitle;
      body = detailMessage || t.workspace.banners.networkErrorBody;
      break;
  }

  const showRetryButton =
    onRetry !== undefined &&
    (kind === "degraded" ||
      kind === "rate_limit" ||
      kind === "network_error" ||
      kind === "generic_error");

  return (
    <div
      role={role}
      aria-live={role === "alert" ? "assertive" : "polite"}
      className={`min-w-0 rounded-2xl border p-3.5 text-xs shadow-xs ${styleClass}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="font-bold">{title}</p>
          <p dir="auto" className="break-words leading-relaxed opacity-90">
            {body}
          </p>
        </div>

        {showRetryButton && (
          <button
            type="button"
            onClick={onRetry}
            disabled={isRetrying}
            className="shrink-0 rounded-lg border border-current/30 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-900 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
          >
            {t.workspace.banners.retryButton}
          </button>
        )}
      </div>
    </div>
  );
}
