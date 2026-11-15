"use client";

import { TriangleAlert } from "lucide-react";
import { ERROR_TEXT, type ErrorLocale } from "@/lib/i18n/errors";

/**
 * What a visitor sees when a page could not read its data: a plain statement and a retry, never a
 * stack trace and never a blank or zero-filled page that could pass for real figures.
 */
export function ErrorScreen({ locale, retry }: { locale: ErrorLocale; retry: () => void }) {
  const t = ERROR_TEXT[locale];
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-line bg-surface-2 p-6">
      <TriangleAlert aria-hidden="true" size={20} strokeWidth={1.75} className="text-faint" />
      <h1 className="text-lg font-semibold tracking-tight">{t.title}</h1>
      <p className="max-w-[60ch] text-sm text-muted">{t.body}</p>
      <button
        type="button"
        onClick={retry}
        className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-2"
      >
        {t.retry}
      </button>
    </div>
  );
}
