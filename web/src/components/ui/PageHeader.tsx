import type { ReactNode } from "react";

interface Props {
  title: string;
  description: string;
  /** Right-aligned slot, e.g. a freshness badge. */
  meta?: ReactNode;
}

export function PageHeader({ title, description, meta }: Props) {
  return (
    <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-[68ch]">
        <h1 className="text-xl font-semibold tracking-tight text-balance sm:text-2xl">{title}</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted text-pretty">{description}</p>
      </div>
      {meta ? <div className="shrink-0">{meta}</div> : null}
    </header>
  );
}
