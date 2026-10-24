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
}

/**
 * The text equivalent of a chart: native <details>, so it works without JavaScript.
 * Numbers use tabular figures so columns line up.
 */
export function DataTable({ caption, columns, rows, showLabel, hideLabel }: Props) {
  return (
    <details className="group mt-4 border-t border-line pt-3">
      <summary className="cursor-pointer select-none rounded text-sm font-medium text-muted hover:text-ink">
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
  );
}
