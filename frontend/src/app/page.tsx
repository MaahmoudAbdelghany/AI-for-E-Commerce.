"use client";

import { AppShell } from "@/components/shell/AppShell";
import { useShopSession } from "@/context/ShopSessionContext";

function WorkspaceSlotPlaceholder() {
  const { t, activeMarket, store, parsedMaxBudget, language } = useShopSession();
  const marketName = language === "ar" ? activeMarket.name_ar : activeMarket.name_en;

  return (
    <section
      aria-label={t.shell.workspaceSlotTitle}
      className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 shadow-xs"
    >
      <h2 className="text-base font-semibold text-slate-900">{t.shell.workspaceSlotTitle}</h2>
      <p className="mt-2 text-sm text-slate-600">{t.shell.workspaceSlotDescription}</p>
      <p className="mt-1 text-xs text-slate-500">{t.shell.workspaceSlotHint}</p>
      <dl className="mt-4 flex flex-wrap gap-3 text-xs text-slate-700">
        <div className="rounded-lg bg-slate-100 px-3 py-1.5">
          <dt className="inline font-semibold">{t.shell.marketLabel}: </dt>
          <dd className="inline">
            {marketName} ({activeMarket.currency})
          </dd>
        </div>
        <div className="rounded-lg bg-slate-100 px-3 py-1.5">
          <dt className="inline font-semibold">{t.shell.storeLabel}: </dt>
          <dd className="inline">{t.shell.stores[store]}</dd>
        </div>
        {parsedMaxBudget && (
          <div className="rounded-lg bg-slate-100 px-3 py-1.5">
            <dt className="inline font-semibold">{t.shell.budgetLabel}: </dt>
            <dd className="inline" dir="ltr">
              {parsedMaxBudget} {activeMarket.currency}
            </dd>
          </div>
        )}
      </dl>
    </section>
  );
}

export default function HomePage() {
  return (
    <AppShell>
      <WorkspaceSlotPlaceholder />
    </AppShell>
  );
}
