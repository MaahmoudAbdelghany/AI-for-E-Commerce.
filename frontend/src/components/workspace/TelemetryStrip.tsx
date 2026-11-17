"use client";

import type { CatalogSourceMode, RankingResult, UiLanguage } from "@/lib/contracts";
import { formatLatencyMs } from "@/lib/format";
import type { TranslationDictionary } from "@/lib/i18n";

export interface TelemetryStripProps {
  sourceMode: CatalogSourceMode | null;
  cacheHit: boolean;
  llmCalls: number;
  latencyMs: number;
  requestId: string;
  rankingResult: RankingResult | null;
  language: UiLanguage;
  t: TranslationDictionary;
}

/**
 * Grounded provenance, cost, cache, and filter telemetry bar for the active result.
 */
export function TelemetryStrip({
  sourceMode,
  cacheHit,
  llmCalls,
  latencyMs,
  requestId,
  rankingResult,
  language,
  t,
}: TelemetryStripProps) {
  const sourceLabel =
    sourceMode === "seed"
      ? t.workspace.telemetry.sourceSeed
      : sourceMode === "live"
        ? t.workspace.telemetry.sourceLive
        : t.workspace.telemetry.sourceSaved;

  return (
    <section
      aria-label={t.workspace.telemetry.title}
      className="min-w-0 rounded-2xl border border-slate-200 bg-white p-3 shadow-xs"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
        <h3 className="text-xs font-bold text-slate-700">{t.workspace.telemetry.title}</h3>
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
              sourceMode === "live"
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : sourceMode === "seed"
                  ? "border-amber-200 bg-amber-50 text-amber-900"
                  : "border-slate-300 bg-slate-100 text-slate-800"
            }`}
          >
            {sourceLabel}
          </span>
          <span
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
              cacheHit
                ? "border-sky-200 bg-sky-50 text-sky-900"
                : "border-slate-200 bg-slate-50 text-slate-700"
            }`}
          >
            {cacheHit ? t.workspace.telemetry.cacheHit : t.workspace.telemetry.cacheMiss}
          </span>
        </div>
      </div>

      <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-slate-700">
        <div className="flex items-center gap-1">
          <dt className="text-slate-500">{t.workspace.telemetry.llmCalls}:</dt>
          <dd className="font-semibold text-slate-900" dir="ltr">
            {llmCalls}
          </dd>
        </div>

        <div className="flex items-center gap-1">
          <dt className="text-slate-500">{t.workspace.telemetry.latency}:</dt>
          <dd className="font-semibold text-slate-900">{formatLatencyMs(latencyMs, language)}</dd>
        </div>

        {rankingResult && (
          <>
            <div className="flex items-center gap-1">
              <dt className="text-slate-500">{t.workspace.telemetry.totalCandidates}:</dt>
              <dd className="font-semibold text-slate-900" dir="ltr">
                {rankingResult.total_candidates}
              </dd>
            </div>
            <div className="flex items-center gap-1">
              <dt className="text-slate-500">{t.workspace.telemetry.filteredAccessories}:</dt>
              <dd className="font-semibold text-slate-900" dir="ltr">
                {rankingResult.filtered_accessories_count}
              </dd>
            </div>
            <div className="flex items-center gap-1">
              <dt className="text-slate-500">{t.workspace.telemetry.filteredOutliers}:</dt>
              <dd className="font-semibold text-slate-900" dir="ltr">
                {rankingResult.filtered_outliers_count}
              </dd>
            </div>
          </>
        )}

        {requestId && (
          <div className="flex min-w-0 items-center gap-1">
            <dt className="shrink-0 text-slate-500">{t.workspace.telemetry.requestId}:</dt>
            <dd className="min-w-0">
              <code dir="ltr" className="break-all rounded bg-slate-100 px-1.5 py-0.5 text-[11px]">
                {requestId}
              </code>
            </dd>
          </div>
        )}
      </dl>
    </section>
  );
}
