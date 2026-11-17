"use client";

import type { WorkspaceMode } from "@/lib/contracts";
import type { TranslationDictionary } from "@/lib/i18n";

export interface ModeToggleProps {
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
  disabled?: boolean;
  t: TranslationDictionary;
}

/**
 * Accessible bilingual segmented switcher toggling between Conversational Assistant
 * (`POST /api/v1/chat`) and Zero-LLM Direct Search (`POST /api/v1/search`).
 */
export function ModeToggle({ mode, onModeChange, disabled = false, t }: ModeToggleProps) {
  const options: Array<{ id: WorkspaceMode; label: string; desc: string }> = [
    {
      id: "chat",
      label: t.workspace.chatModeLabel,
      desc: t.workspace.chatModeDesc,
    },
    {
      id: "search",
      label: t.workspace.searchModeLabel,
      desc: t.workspace.searchModeDesc,
    },
  ];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-2 shadow-xs">
      <div
        role="tablist"
        aria-label={t.workspace.modeToggleLabel}
        className="grid grid-cols-1 gap-1.5 sm:grid-cols-2"
      >
        {options.map((option) => {
          const selected = mode === option.id;
          return (
            <button
              key={option.id}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-label={option.label}
              disabled={disabled}
              onClick={() => onModeChange(option.id)}
              className={`min-w-0 rounded-xl border px-3 py-2 text-start transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:cursor-not-allowed disabled:opacity-60 ${
                selected
                  ? "border-teal-700 bg-teal-700 text-white shadow-xs"
                  : "border-transparent bg-slate-50 text-slate-800 hover:border-slate-300 hover:bg-slate-100"
              }`}
            >
              <span className="block text-xs font-bold">{option.label}</span>
              <span
                className={`mt-0.5 block text-[11px] leading-snug ${
                  selected ? "text-teal-50" : "text-slate-600"
                }`}
              >
                {option.desc}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
