"use client";

import type { RankedOffer, UiLanguage } from "@/lib/contracts";
import type { TranslationDictionary } from "@/lib/i18n";

import { OfferCard } from "./OfferCard";

export interface ProductComparisonGridProps {
  rankedOffers: RankedOffer[];
  language: UiLanguage;
  t: TranslationDictionary;
  queryLabel?: string;
  hasActiveComparison?: boolean;
}

/**
 * Strictly grounded comparison grid rendering `1–3` server-ordered `RankedOffer` cards
 * with zero client-side re-sorting, math, or synthetic padding (`INV-03`, `INV-05`).
 */
export function ProductComparisonGrid({
  rankedOffers,
  language,
  t,
  queryLabel,
  hasActiveComparison = false,
}: ProductComparisonGridProps) {
  if (rankedOffers.length === 0) {
    if (hasActiveComparison) {
      return null;
    }

    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center shadow-xs">
        <h2 className="text-base font-bold text-slate-900">
          {t.workspace.comparison.panelEmptyTitle}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          {t.workspace.comparison.panelEmptyBody}
        </p>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 space-y-0.5">
          <h2 className="text-base font-bold text-slate-900">
            {t.workspace.comparison.panelTitle}
          </h2>
          {queryLabel && (
            <p dir="auto" className="break-words text-xs text-slate-600">
              {queryLabel}
            </p>
          )}
        </div>
        <span className="shrink-0 rounded-full border border-teal-200 bg-teal-50 px-2.5 py-0.5 text-xs font-semibold text-teal-900">
          {rankedOffers.length} {t.workspace.comparison.offersFoundLabel}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {rankedOffers.map((item) => (
          <OfferCard
            key={`${item.rank}-${item.offer.offer_id}`}
            rankedOffer={item}
            language={language}
            t={t}
          />
        ))}
      </div>
    </div>
  );
}
