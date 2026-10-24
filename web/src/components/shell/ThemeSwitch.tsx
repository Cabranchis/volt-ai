"use client";

import { Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { useSyncExternalStore } from "react";
import type { Dictionary } from "@/lib/i18n/en";

type Theme = "light" | "dark" | "system";
const STORAGE_KEY = "voltia-theme";
const CHANGE_EVENT = "voltia-theme-change";

function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  try {
    if (theme === "system") localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Storage can be blocked (private windows); the theme still applies for this visit.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function ThemeSwitch({ labels }: { labels: Dictionary["common"] }) {
  // The server cannot know the saved theme, so it renders "system" and the browser corrects it.
  const theme = useSyncExternalStore(subscribe, readStoredTheme, (): Theme => "system");

  const options: { value: Theme; label: string; Icon: LucideIcon }[] = [
    { value: "light", label: labels.themeLight, Icon: Sun },
    { value: "dark", label: labels.themeDark, Icon: Moon },
    { value: "system", label: labels.themeSystem, Icon: Monitor },
  ];

  return (
    <div role="radiogroup" aria-label={labels.theme} className="flex rounded-lg border border-line bg-surface p-0.5">
      {options.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          aria-label={label}
          title={label}
          onClick={() => applyTheme(value)}
          className={[
            "grid h-8 flex-1 place-items-center rounded-md",
            theme === value ? "bg-surface-2 text-ink" : "text-faint hover:text-ink",
          ].join(" ")}
        >
          <Icon aria-hidden="true" size={16} strokeWidth={1.75} />
        </button>
      ))}
    </div>
  );
}
