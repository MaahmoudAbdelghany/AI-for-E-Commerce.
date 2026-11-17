"use client";

import { useShopSession } from "@/context/ShopSessionContext";

export function LanguageToggle() {
  const { language, setLanguage, t } = useShopSession();
  const nextLanguage = language === "ar" ? "en" : "ar";

  return (
    <button
      type="button"
      onClick={() => setLanguage(nextLanguage)}
      aria-label={t.shell.languageToggleLabel}
      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 transition-colors hover:border-teal-700 hover:bg-teal-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
    >
      <span aria-hidden="true">🌐</span>
      <span>{t.shell.switchToLanguageLabel}</span>
    </button>
  );
}
