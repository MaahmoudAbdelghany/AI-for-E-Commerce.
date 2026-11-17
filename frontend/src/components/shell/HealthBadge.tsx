"use client";

import { useShopSession } from "@/context/ShopSessionContext";
import type { HealthStatus } from "@/lib/contracts";

const STATUS_BADGE_STYLES: Record<HealthStatus, { dot: string; badge: string }> = {
  checking: {
    dot: "bg-slate-400",
    badge: "border-slate-300 bg-slate-50 text-slate-700",
  },
  ok: {
    dot: "bg-emerald-600",
    badge: "border-emerald-200 bg-emerald-50 text-emerald-800",
  },
  degraded: {
    dot: "bg-amber-500",
    badge: "border-amber-200 bg-amber-50 text-amber-900",
  },
  offline: {
    dot: "bg-rose-600",
    badge: "border-rose-200 bg-rose-50 text-rose-800",
  },
};

export function HealthBadge() {
  const { healthStatus, health, refreshHealth, t } = useShopSession();
  const style = STATUS_BADGE_STYLES[healthStatus];
  const label = t.shell.health[healthStatus];

  return (
    <div className="inline-flex items-center gap-1.5">
      <div
        role="status"
        aria-live="polite"
        aria-label={`${t.shell.health.label}: ${label}`}
        title={health ? `${health.catalog_mode} / ${health.llm_mode}` : label}
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${style.badge}`}
      >
        <span aria-hidden="true" className={`h-2 w-2 rounded-full ${style.dot}`} />
        <span>{label}</span>
      </div>
      <button
        type="button"
        onClick={() => void refreshHealth()}
        aria-label={t.shell.health.refreshAria}
        className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
      >
        ↻
      </button>
    </div>
  );
}
