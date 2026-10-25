"use client";

import { useId } from "react";

export interface RangeOption<T extends string> {
  value: T;
  label: string;
}

interface Props<T extends string> {
  options: readonly RangeOption<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}

/** Segmented control for choosing a time range. A radio group, so arrow keys move the selection. */
export function RangeControl<T extends string>({ options, value, onChange, label }: Props<T>) {
  const groupId = useId();

  return (
    <div role="radiogroup" aria-label={label} className="glass inline-flex rounded-lg p-0.5">
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <label
            key={option.value}
            className={[
              "relative cursor-pointer rounded-md px-3 py-1.5 text-xs font-medium has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus",
              selected ? "seg-active" : "text-muted hover:text-ink",
            ].join(" ")}
          >
            <input
              type="radio"
              name={groupId}
              value={option.value}
              checked={selected}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            {option.label}
          </label>
        );
      })}
    </div>
  );
}
