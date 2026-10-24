import { useId, type ReactNode } from "react";

interface Props {
  title: string;
  note?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Heading level. Pages use h1 for the title, so panels default to h2. */
  as?: "h2" | "h3";
}

/** Bordered section. Elevation is declared once, by the border (no shadow). */
export function Panel({ title, note, actions, children, className = "", as: Heading = "h2" }: Props) {
  const id = useId();
  return (
    <section
      aria-labelledby={id}
      className={`rounded-panel border border-line bg-surface p-5 sm:p-6 ${className}`}
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <Heading id={id} className="text-lg font-semibold tracking-tight">
            {title}
          </Heading>
          {note ? <p className="mt-0.5 text-sm text-muted">{note}</p> : null}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}
