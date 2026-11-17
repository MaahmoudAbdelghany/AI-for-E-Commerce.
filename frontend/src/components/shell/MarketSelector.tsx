"use client";

import { useShopSession } from "@/context/ShopSessionContext";

export function MarketSelector() {
  const { markets, country, setCountry, language, t } = useShopSession();

  return (
    <div className="min-w-0 flex flex-col gap-1.5">
      <span id="market-selector-label" className="text-xs font-semibold text-slate-600">
        {t.shell.marketLabel}
      </span>
      <div
        role="radiogroup"
        aria-labelledby="market-selector-label"
        className="flex flex-wrap gap-1.5"
      >
        {markets.map((market) => {
          const selected = market.country === country;
          const countryName = language === "ar" ? market.name_ar : market.name_en;
          const currencyLabel =
            language === "ar" ? market.currency_label_ar : market.currency_label_en;

          return (
            <button
              key={market.country}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => setCountry(market.country)}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 ${
                selected
                  ? "border-teal-700 bg-teal-700 text-white shadow-xs"
                  : "border-slate-300 bg-white text-slate-800 hover:border-teal-600 hover:bg-teal-50"
              }`}
            >
              <span>{countryName}</span>
              <span
                className={`rounded px-1 py-0.5 text-[11px] ${
                  selected ? "bg-teal-800/80 text-teal-50" : "bg-slate-100 text-slate-600"
                }`}
              >
                {currencyLabel}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
