"use client";

import type { CountryCode, UiLanguage } from "@/lib/contracts";
import { STARTER_PROMPTS, type TranslationDictionary } from "@/lib/i18n";

export interface StarterPromptsProps {
  country: CountryCode;
  language: UiLanguage;
  disabled?: boolean;
  onSelectPrompt: (queryText: string) => void;
  t: TranslationDictionary;
}

/**
 * Localized per-market (`EG`/`SA`/`AE`) clickable example shopping queries.
 */
export function StarterPrompts({
  country,
  language,
  disabled = false,
  onSelectPrompt,
  t,
}: StarterPromptsProps) {
  const prompts = STARTER_PROMPTS[country];

  return (
    <section
      aria-label={t.workspace.starterPromptsTitle}
      className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-xs"
    >
      <div className="space-y-0.5">
        <h2 className="text-xs font-bold text-slate-800">{t.workspace.starterPromptsTitle}</h2>
        <p className="text-[11px] text-slate-500">{t.workspace.starterPromptsHint}</p>
      </div>

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {prompts.map((prompt) => {
          const chipLabel = language === "ar" ? prompt.labelAr : prompt.labelEn;
          const queryText = language === "ar" ? prompt.queryAr : prompt.queryEn;
          return (
            <button
              key={prompt.id}
              type="button"
              disabled={disabled}
              onClick={() => onSelectPrompt(queryText)}
              title={queryText}
              className="rounded-full border border-teal-200 bg-teal-50/70 px-3 py-1.5 text-xs font-medium text-teal-900 transition-colors hover:border-teal-600 hover:bg-teal-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
            >
              {chipLabel}
            </button>
          );
        })}
      </div>
    </section>
  );
}
