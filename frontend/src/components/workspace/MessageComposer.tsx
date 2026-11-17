"use client";

import type { FormEvent, KeyboardEvent } from "react";

import type { WorkspaceMode } from "@/lib/contracts";
import type { TranslationDictionary } from "@/lib/i18n";

export interface MessageComposerProps {
  mode: WorkspaceMode;
  chatInput: string;
  onChatInputChange: (value: string) => void;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  minRating: number | null;
  onMinRatingChange: (value: number | null) => void;
  includeAccessories: boolean;
  onIncludeAccessoriesChange: (checked: boolean) => void;
  isSubmitting: boolean;
  canCompareSaved: boolean;
  validationError: string | null;
  onSubmitChat: () => void;
  onSubmitSearch: () => void;
  onCompareSaved: () => void;
  t: TranslationDictionary;
}

const MIN_RATING_OPTIONS = ["3", "3.5", "4", "4.5", "5"] as const;

/**
 * Dual-mode composer handling Conversational Assistant turns (`Enter` / Send +
 * Compare Saved Offers CTA) and Zero-LLM Direct Search controls (`min_rating`,
 * `include_accessories`) with inline validation errors.
 */
export function MessageComposer({
  mode,
  chatInput,
  onChatInputChange,
  searchQuery,
  onSearchQueryChange,
  minRating,
  onMinRatingChange,
  includeAccessories,
  onIncludeAccessoriesChange,
  isSubmitting,
  canCompareSaved,
  validationError,
  onSubmitChat,
  onSubmitSearch,
  onCompareSaved,
  t,
}: MessageComposerProps) {
  function handleFormSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting) {
      return;
    }
    if (mode === "chat") {
      onSubmitChat();
    } else {
      onSubmitSearch();
    }
  }

  function handleTextareaKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!isSubmitting) {
        onSubmitChat();
      }
    }
  }

  return (
    <form
      onSubmit={handleFormSubmit}
      className="min-w-0 space-y-3 rounded-2xl border border-slate-200 bg-white p-3.5 shadow-xs"
    >
      {mode === "chat" ? (
        <div className="space-y-1.5">
          <label
            htmlFor="chat-composer-input"
            className="block text-xs font-semibold text-slate-700"
          >
            {t.workspace.composer.chatLabel}
          </label>
          <textarea
            id="chat-composer-input"
            dir="auto"
            rows={3}
            value={chatInput}
            onChange={(event) => onChatInputChange(event.target.value)}
            onKeyDown={handleTextareaKeyDown}
            placeholder={t.workspace.composer.chatPlaceholder}
            aria-invalid={validationError !== null}
            aria-describedby={validationError ? "composer-validation-error" : undefined}
            className={`w-full min-w-0 resize-y rounded-xl border bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-2 focus:outline-offset-1 ${
              validationError
                ? "border-rose-600 focus:outline-rose-600"
                : "border-slate-300 focus:border-teal-700 focus:outline-teal-700"
            }`}
          />
        </div>
      ) : (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label
              htmlFor="direct-search-input"
              className="block text-xs font-semibold text-slate-700"
            >
              {t.workspace.composer.searchLabel}
            </label>
            <input
              id="direct-search-input"
              type="text"
              dir="auto"
              value={searchQuery}
              onChange={(event) => onSearchQueryChange(event.target.value)}
              placeholder={t.workspace.composer.searchPlaceholder}
              aria-invalid={validationError !== null}
              aria-describedby={validationError ? "composer-validation-error" : undefined}
              className={`w-full min-w-0 rounded-xl border bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-2 focus:outline-offset-1 ${
                validationError
                  ? "border-rose-600 focus:outline-rose-600"
                  : "border-slate-300 focus:border-teal-700 focus:outline-teal-700"
              }`}
            />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:items-end">
            <div className="space-y-1">
              <label
                htmlFor="min-rating-select"
                className="block text-xs font-semibold text-slate-700"
              >
                {t.workspace.composer.minRatingLabel}
              </label>
              <select
                id="min-rating-select"
                value={minRating === null ? "" : String(minRating)}
                onChange={(event) => {
                  const val = event.target.value;
                  onMinRatingChange(val === "" ? null : Number(val));
                }}
                className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-900 focus:border-teal-700 focus:outline-2 focus:outline-offset-1 focus:outline-teal-700"
              >
                <option value="">{t.workspace.composer.minRatingAny}</option>
                <option value="0">0.0+</option>
                {MIN_RATING_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}+
                  </option>
                ))}
              </select>
            </div>

            <label
              htmlFor="include-accessories-checkbox"
              className="flex cursor-pointer items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-800 hover:bg-slate-100"
            >
              <input
                id="include-accessories-checkbox"
                type="checkbox"
                checked={includeAccessories}
                onChange={(event) => onIncludeAccessoriesChange(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-teal-700 focus:ring-teal-700"
              />
              <span>{t.workspace.composer.includeAccessoriesLabel}</span>
            </label>
          </div>
        </div>
      )}

      {validationError && (
        <p
          id="composer-validation-error"
          role="alert"
          className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-800"
        >
          {validationError}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        {mode === "chat" && canCompareSaved ? (
          <button
            type="button"
            disabled={isSubmitting}
            onClick={onCompareSaved}
            title={t.workspace.composer.compareSavedHint}
            className="rounded-xl border border-teal-700 bg-teal-50 px-3 py-2 text-xs font-semibold text-teal-900 transition-colors hover:bg-teal-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
          >
            {t.workspace.composer.compareSavedButton}
          </button>
        ) : (
          <span />
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="inline-flex items-center justify-center rounded-xl bg-teal-700 px-4 py-2 text-xs font-semibold text-white shadow-xs transition-colors hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
        >
          {isSubmitting
            ? t.workspace.composer.sendingButton
            : mode === "chat"
              ? t.workspace.composer.sendButton
              : t.workspace.composer.searchButton}
        </button>
      </div>
    </form>
  );
}
