import { ChevronRight, Download } from "lucide-react";
import type { ReactNode } from "react";

export interface Column {
  key: string;
  header: string;
  align?: "left" | "right";
}

interface Props {
  caption: string;
  columns: readonly Column[];
  rows: readonly Record<string, ReactNode>[];
  showLabel: string;
  hideLabel: string;
  /** A download of the same data as a spreadsheet file. */
  csv?: { href: string; label: string };
}

/**
 * The text equivalent of a chart: native <details>, so it works without JavaScript.
 * Numbers use tabular figures so columns line up.
 */
export function DataTable({
  caption,
  columns,
  rows,
  showLabel,
  hideLabel,
  csv,
}: Props) {
  return (
    <div className="relative mt-4 border-t border-line pt-3">
      {csv ? (
        <a
          href={csv.href}
          download
          className="btn-glass absolute right-0 top-2.5 z-10 inline-flex min-h-9 items-center gap-1.5 rounded-md px-3 text-xs font-medium text-muted hover:text-ink"
        >
          <Download aria-hidden="true" size={14} strokeWidth={2} />
          {csv.label}
        </a>
      ) : null}
      <details className="group">
        <summary className="flex cursor-pointer select-none list-none items-center gap-1.5 rounded py-1.5 text-sm font-medium text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
          <ChevronRight aria-hidden="true" size={14} strokeWidth={2} className="transition-transform group-open:rotate-90 motion-reduce:transition-none" />
          <span className="group-open:hidden">{showLabel}</span>
          <span className="hidden group-open:inline">{hideLabel}</span>
        </summary>
        {/* Focusable so keyboard users can scroll a wide or tall table. */}
        <div
          tabIndex={0}
          role="region"
          aria-label={caption}
          className="mt-3 max-h-80 overflow-auto rounded-lg border border-line"
        >
          <table className="w-full min-w-max border-collapse text-sm tabular-nums">
            <caption className="sr-only">{caption}</caption>
            <thead className="sticky top-0 bg-surface-2 text-xs text-muted">
              <tr>
                {columns.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    className={`px-3 py-2 font-medium ${column.align === "right" ? "text-right" : "text-left"}`}
                  >
                    {column.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-t border-line">
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={`px-3 py-1.5 ${column.align === "right" ? "text-right" : "text-left"}`}
                    >
                      {row[column.key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
