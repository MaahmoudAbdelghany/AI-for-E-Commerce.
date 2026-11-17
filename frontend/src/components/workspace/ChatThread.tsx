"use client";

import { useEffect, useRef } from "react";

import type { ChatMessageItem } from "@/lib/contracts";
import type { TranslationDictionary } from "@/lib/i18n";

export interface ChatThreadProps {
  messages: ChatMessageItem[];
  isLoading: boolean;
  t: TranslationDictionary;
}

/**
 * Bilingual RTL/LTR (`dir="auto"`) chat timeline with turn metadata badges,
 * accessible loading skeleton, and jsdom-safe auto-scroll.
 */
export function ChatThread({ messages, isLoading, t }: ChatThreadProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const target = endRef.current;
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [messages.length, isLoading]);

  return (
    <section
      aria-label={t.workspace.chatThreadLabel}
      className="flex max-h-[420px] min-h-[220px] flex-col gap-3 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-3.5 shadow-xs"
    >
      {messages.length === 0 && !isLoading ? (
        <div className="my-auto py-6 text-center">
          <p className="text-sm font-bold text-slate-800">{t.workspace.emptyChatTitle}</p>
          <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
            {t.workspace.emptyChatBody}
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {messages.map((msg) => {
            const isUser = msg.role === "user";
            const senderLabel = isUser ? t.workspace.userRoleLabel : t.workspace.assistantRoleLabel;
            const actionLabel = msg.action ? t.workspace.turnActions[msg.action] : null;
            const statusLabel = msg.status ? t.workspace.turnStatuses[msg.status] : null;

            return (
              <li
                key={msg.id}
                className={`flex min-w-0 flex-col gap-1.5 rounded-2xl border p-3 ${
                  isUser
                    ? "ms-6 border-teal-200 bg-teal-50/70 text-slate-900"
                    : "me-6 border-slate-200 bg-slate-50 text-slate-900"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-1.5">
                  <span className="text-[11px] font-bold text-slate-700">{senderLabel}</span>

                  {!isUser && (actionLabel || statusLabel || (msg.offerCount ?? 0) > 0) && (
                    <div className="flex flex-wrap items-center gap-1">
                      {actionLabel && (
                        <span className="rounded-md border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-700">
                          {actionLabel}
                        </span>
                      )}
                      {statusLabel && (
                        <span
                          className={`rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${
                            msg.status === "ok"
                              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                              : msg.status === "refused" || msg.status === "degraded"
                                ? "border-rose-200 bg-rose-50 text-rose-800"
                                : "border-amber-200 bg-amber-50 text-amber-900"
                          }`}
                        >
                          {statusLabel}
                        </span>
                      )}
                      {typeof msg.offerCount === "number" && msg.offerCount > 0 && (
                        <span className="rounded-md border border-teal-200 bg-teal-50 px-1.5 py-0.5 text-[10px] font-semibold text-teal-900">
                          {msg.offerCount} {t.workspace.offersCountBadge}
                        </span>
                      )}
                    </div>
                  )}
                </div>

                <p
                  dir="auto"
                  className="min-w-0 whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-900"
                >
                  {msg.content}
                </p>
              </li>
            );
          })}
        </ul>
      )}

      {isLoading && (
        <div
          role="status"
          aria-live="polite"
          className="me-6 space-y-2 rounded-2xl border border-teal-200 bg-teal-50/40 p-3 text-xs text-teal-900"
        >
          <p className="font-semibold">{t.workspace.loadingResponse}</p>
          <div className="space-y-1.5" aria-hidden="true">
            <div className="h-2.5 w-3/4 animate-pulse rounded bg-teal-200/70" />
            <div className="h-2.5 w-1/2 animate-pulse rounded bg-teal-200/60" />
          </div>
        </div>
      )}

      <div ref={endRef} />
    </section>
  );
}
