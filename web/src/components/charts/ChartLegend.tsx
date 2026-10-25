export interface LegendItem {
  label: string;
  /** CSS colour (a token such as var(--c-demand)). */
  color: string;
  kind: "line" | "dashed" | "dotted" | "area" | "bar";
}

/**
 * A legend is always shown for two or more series, so identity never depends on colour alone.
 * Text stays in the text colour; only the key beside it carries the series colour.
 */
export function ChartLegend({ items }: { items: readonly LegendItem[] }) {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-2">
          <Key item={item} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

function Key({ item }: { item: LegendItem }) {
  const style = { background: item.color };
  if (item.kind === "area") {
    return (
      <span
        aria-hidden="true"
        className="h-3 w-5 rounded-[3px] border"
        style={{
          background: `color-mix(in srgb, ${item.color} 24%, transparent)`,
          borderColor: `color-mix(in srgb, ${item.color} 50%, transparent)`,
        }}
      />
    );
  }
  if (item.kind === "bar") {
    return <span aria-hidden="true" className="h-3 w-3 rounded-[3px]" style={style} />;
  }
  if (item.kind === "dotted") {
    return (
      <span
        aria-hidden="true"
        className="h-0.5 w-5"
        style={{
          backgroundImage: `repeating-linear-gradient(90deg, ${item.color} 0 2px, transparent 2px 5px)`,
        }}
      />
    );
  }
  if (item.kind === "dashed") {
    return (
      <span
        aria-hidden="true"
        className="h-0.5 w-5"
        style={{
          backgroundImage: `repeating-linear-gradient(90deg, ${item.color} 0 5px, transparent 5px 8px)`,
        }}
      />
    );
  }
  return <span aria-hidden="true" className="h-0.5 w-5 rounded-full" style={style} />;
}
