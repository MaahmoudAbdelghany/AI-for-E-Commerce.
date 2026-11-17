"use client";

import { useState } from "react";

import type { RankedOffer, UiLanguage } from "@/lib/contracts";
import {
  formatBayesianScore,
  formatExactPrice,
  formatRatingValue,
  formatValueScore,
  sanitizeHttpsUrl,
} from "@/lib/format";
import {
  getMatchReasonLabel,
  STORE_LABELS,
  type TranslationDictionary,
} from "@/lib/i18n";

export interface OfferCardProps {
  rankedOffer: RankedOffer;
  language: UiLanguage;
  t: TranslationDictionary;
}

/**
 * Strictly grounded comparison card rendering server-ordered offer metrics,
 * validated `https://` image fallback, and safe `rel="noopener noreferrer"` store CTA.
 */
export function OfferCard({ rankedOffer, language, t }: OfferCardProps) {
  const { offer, rank, value_score, bayesian_rating, match_reasons } = rankedOffer;
  const [failedImageUrl, setFailedImageUrl] = useState<string | null>(null);

  const safeImageUrl = sanitizeHttpsUrl(offer.image_url);
  const showImage = safeImageUrl !== null && failedImageUrl !== safeImageUrl;
  const safeOfferUrl = sanitizeHttpsUrl(offer.url);

  const storeLabel = STORE_LABELS[offer.store][language];
  const isUnrated =
    offer.rating === null || !Number.isFinite(offer.rating) || offer.review_count <= 0;
  const clampedValueScore = Number.isFinite(value_score)
    ? Math.min(100, Math.max(0, value_score))
    : 0;
  const progressValue = Number(clampedValueScore.toFixed(1));

  return (
    <article
      aria-label={`${t.workspace.comparison.rankPrefix}${rank} ${offer.title}`}
      className="flex min-w-0 flex-col justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-3.5 shadow-xs transition-shadow hover:shadow-md"
    >
      <div className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="inline-flex items-center rounded-full bg-teal-700 px-2.5 py-0.5 text-xs font-bold text-white">
              {t.workspace.comparison.rankPrefix}
              {rank}
            </span>
            <span
              className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                offer.store === "noon"
                  ? "border-amber-300 bg-amber-50 text-amber-900"
                  : "border-sky-300 bg-sky-50 text-sky-900"
              }`}
            >
              {storeLabel}
            </span>
          </div>

          {!offer.in_stock && (
            <span className="inline-flex items-center rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-800">
              {t.workspace.comparison.outOfStockBadge}
            </span>
          )}
        </div>

        <div className="flex h-36 w-full items-center justify-center overflow-hidden rounded-xl border border-slate-100 bg-slate-50 p-2">
          {showImage ? (
            <img
              src={safeImageUrl}
              alt={offer.title}
              loading="lazy"
              referrerPolicy="no-referrer"
              onError={() => setFailedImageUrl(safeImageUrl)}
              className="h-full w-full object-contain"
            />
          ) : (
            <svg
              role="img"
              aria-label={t.workspace.comparison.imageFallbackAlt}
              viewBox="0 0 64 64"
              className="h-14 w-14 text-slate-400"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect x="10" y="14" width="44" height="36" rx="4" />
              <path d="M18 40l10-10 8 8 6-6 4 8" />
              <circle cx="24" cy="25" r="3" />
            </svg>
          )}
        </div>

        <div className="min-w-0 space-y-1">
          <h3
            dir="auto"
            className="min-w-0 break-words text-sm font-bold leading-snug text-slate-900"
          >
            {offer.title}
          </h3>
          <p className="text-lg font-extrabold text-teal-800" dir="auto">
            {formatExactPrice(offer.price, offer.currency, language)}
          </p>
        </div>

        <dl className="space-y-1.5 rounded-xl border border-slate-100 bg-slate-50/70 p-2.5 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-1">
            <dt className="font-medium text-slate-600">{t.workspace.comparison.rawRatingLabel}</dt>
            <dd className="font-semibold text-slate-900">
              {isUnrated ? (
                <span className="inline-flex items-center rounded-md border border-slate-300 bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-700">
                  {t.workspace.comparison.unratedBadge}
                </span>
              ) : (
                <span dir="auto">{formatRatingValue(offer.rating, offer.review_count, language)}</span>
              )}
            </dd>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-1">
            <dt className="font-medium text-slate-600">
              {t.workspace.comparison.bayesianRatingLabel}
            </dt>
            <dd className="font-semibold text-slate-900" dir="ltr">
              {formatBayesianScore(bayesian_rating)}
            </dd>
          </div>
        </dl>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="font-medium text-slate-600">
              {t.workspace.comparison.valueScoreLabel}
            </span>
            <span className="font-bold text-slate-900" dir="ltr">
              {formatValueScore(value_score)}
            </span>
          </div>
          <div
            role="progressbar"
            aria-label={t.workspace.comparison.valueScoreLabel}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressValue}
            className="h-2 w-full overflow-hidden rounded-full bg-slate-200"
          >
            <div
              className="h-full rounded-full bg-teal-700 transition-all"
              style={{ width: `${clampedValueScore}%` }}
            />
          </div>
        </div>

        {match_reasons.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {match_reasons.map((reasonCode, index) => (
              <li
                key={`${reasonCode}-${index}`}
                className="rounded-md border border-teal-200 bg-teal-50 px-2 py-0.5 text-[11px] font-medium text-teal-900"
              >
                {getMatchReasonLabel(reasonCode, language)}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="pt-1">
        {safeOfferUrl ? (
          <a
            href={safeOfferUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex w-full items-center justify-center rounded-lg bg-teal-700 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
          >
            {t.workspace.comparison.openStoreCta}
          </a>
        ) : (
          <button
            type="button"
            disabled
            aria-disabled="true"
            className="inline-flex w-full cursor-not-allowed items-center justify-center rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-xs font-medium text-slate-500"
          >
            {t.workspace.comparison.unavailableLinkCta}
          </button>
        )}
      </div>
    </article>
  );
}
