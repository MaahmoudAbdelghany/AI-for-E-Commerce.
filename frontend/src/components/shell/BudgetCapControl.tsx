"use client";

import { useShopSession } from "@/context/ShopSessionContext";

export function BudgetCapControl() {
  const { maxBudget, setMaxBudget, budgetError, activeMarket, language, t } = useShopSession();
  const currencyLabel =
    language === "ar" ? activeMarket.currency_label_ar : activeMarket.currency_label_en;
  const errorText = budgetError ? t.shell.budgetErrors[budgetError] : null;

  return (
    <div className="min-w-0 flex flex-col gap-1.5">
      <label htmlFor="budget-cap-input" className="text-xs font-semibold text-slate-600">
        {t.shell.budgetLabel} ({currencyLabel})
      </label>
      <div className="flex items-center gap-1.5">
        <input
          id="budget-cap-input"
          type="text"
          inputMode="decimal"
          dir="ltr"
          value={maxBudget}
          onChange={(event) => setMaxBudget(event.target.value)}
          placeholder={t.shell.budgetPlaceholder}
          aria-invalid={errorText !== null}
          aria-describedby={errorText ? "budget-cap-error" : "budget-cap-hint"}
          className={`w-full min-w-0 rounded-lg border bg-white px-3 py-1.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-2 focus:outline-offset-1 ${
            errorText
              ? "border-rose-600 focus:outline-rose-600"
              : "border-slate-300 focus:border-teal-700 focus:outline-teal-700"
          }`}
        />
        {maxBudget.length > 0 && (
          <button
            type="button"
            onClick={() => setMaxBudget("")}
            aria-label={t.shell.budgetClear}
            className="shrink-0 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
          >
            {t.shell.budgetClear}
          </button>
        )}
      </div>
      {errorText ? (
        <p id="budget-cap-error" role="alert" className="text-xs font-medium text-rose-700">
          {errorText}
        </p>
      ) : (
        <p id="budget-cap-hint" className="text-[11px] text-slate-500">
          {t.shell.budgetHint}
        </p>
      )}
    </div>
  );
}
