"use client";

import { useShopSession } from "@/context/ShopSessionContext";
import { SUPPORTED_STORE_FILTERS, type StoreFilter } from "@/lib/contracts";

export function StoreFilterBar() {
  const { store, setStore, t } = useShopSession();

  return (
    <div className="min-w-0 flex flex-col gap-1.5">
      <span id="store-filter-label" className="text-xs font-semibold text-slate-600">
        {t.shell.storeLabel}
      </span>
      <div
        role="radiogroup"
        aria-labelledby="store-filter-label"
        className="flex flex-wrap gap-1.5"
      >
        {SUPPORTED_STORE_FILTERS.map((option: StoreFilter) => {
          const selected = store === option;
          return (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => setStore(option)}
              className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 ${
                selected
                  ? "border-slate-900 bg-slate-900 text-white shadow-xs"
                  : "border-slate-300 bg-white text-slate-800 hover:border-slate-500 hover:bg-slate-50"
              }`}
            >
              {t.shell.stores[option]}
            </button>
          );
        })}
      </div>
    </div>
  );
}
