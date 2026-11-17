"use client";

import type { ReactNode } from "react";

import { BudgetCapControl } from "@/components/shell/BudgetCapControl";
import { HealthBadge } from "@/components/shell/HealthBadge";
import { LanguageToggle } from "@/components/shell/LanguageToggle";
import { MarketSelector } from "@/components/shell/MarketSelector";
import { StoreFilterBar } from "@/components/shell/StoreFilterBar";
import { useShopSession } from "@/context/ShopSessionContext";

export function AppShell({ children }: { children: ReactNode }) {
  const { t, marketsError, resetActiveMarketSession } = useShopSession();

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <a
        href="#main-workspace"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:z-50 focus:rounded-md focus:bg-teal-700 focus:px-3 focus:py-2 focus:text-xs focus:font-semibold focus:text-white"
      >
        {t.brand.skipToMain}
      </a>

      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-3 py-3 sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <h1 className="text-lg font-bold tracking-tight text-slate-900 sm:text-xl">
                {t.brand.title}
              </h1>
              <p className="mt-0.5 text-xs text-slate-600 sm:text-sm">{t.brand.subtitle}</p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <HealthBadge />
              <LanguageToggle />
              <button
                type="button"
                onClick={resetActiveMarketSession}
                aria-label={t.shell.newChatAria}
                className="rounded-lg border border-teal-700 bg-white px-3 py-1.5 text-xs font-semibold text-teal-800 transition-colors hover:bg-teal-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
              >
                {t.shell.newChat}
              </button>
            </div>
          </div>

          <section
            aria-label={t.shell.controlsRegionLabel}
            className="grid grid-cols-1 gap-3 border-t border-slate-100 pt-3 md:grid-cols-12 md:items-start"
          >
            <div className="min-w-0 md:col-span-5">
              <MarketSelector />
            </div>
            <div className="min-w-0 md:col-span-4">
              <StoreFilterBar />
            </div>
            <div className="min-w-0 md:col-span-3">
              <BudgetCapControl />
            </div>
          </section>

          {marketsError && (
            <p
              role="status"
              className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-900"
            >
              {t.shell.marketsFallbackNotice}
            </p>
          )}
        </div>
      </header>

      <main id="main-workspace" className="mx-auto w-full max-w-7xl px-3 py-4 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  );
}
