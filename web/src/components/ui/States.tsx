import { DatabaseZap } from "lucide-react";

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-lg border border-dashed border-line bg-surface-2 p-6">
      <DatabaseZap aria-hidden="true" size={20} strokeWidth={1.75} className="text-faint" />
      <p className="font-medium">{title}</p>
      <p className="max-w-[60ch] text-sm text-muted">{body}</p>
    </div>
  );
}

/** Placeholder with the final chart's footprint, so the page does not jump when data arrives. */
export function ChartSkeleton({ height = 340 }: { height?: number }) {
  return <div className="skeleton w-full" style={{ height }} aria-hidden="true" />;
}

export function TextSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="flex flex-col gap-2" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton h-4" style={{ width: `${100 - i * 12}%` }} />
      ))}
    </div>
  );
}
