"use client";

import {
  Activity,
  BrainCircuit,
  Briefcase,
  Calculator,
  CloudRain,
  Gauge,
  Info,
  LayoutDashboard,
  Map as MapIcon,
  MessageSquareText,
  Zap,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { hrefFor, NAV_ITEMS, type NavItem } from "@/lib/site";

const ICONS: Record<NavItem["key"], LucideIcon> = {
  overview: LayoutDashboard,
  demand: Zap,
  price: Gauge,
  hydrology: CloudRain,
  map: MapIcon,
  anomalies: Activity,
  models: BrainCircuit,
  analyst: MessageSquareText,
  calculator: Calculator,
  business: Briefcase,
  about: Info,
};

interface Props {
  locale: Locale;
  labels: Dictionary["nav"];
  onNavigate?: () => void;
}

export function NavLinks({ locale, labels, onNavigate }: Props) {
  const pathname = usePathname();

  return (
    <nav aria-label={labels.label}>
      <ul className="flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => {
          const href = hrefFor(locale, item.path);
          const current = item.path === "" ? pathname === href : pathname.startsWith(href);
          const Icon = ICONS[item.key];
          return (
            <li key={item.key}>
              <Link
                href={href}
                onClick={onNavigate}
                aria-current={current ? "page" : undefined}
                className={[
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium",
                  current
                    ? "seg-active"
                    : "text-muted hover:bg-[var(--glass)] hover:text-ink",
                ].join(" ")}
              >
                <Icon
                  aria-hidden="true"
                  size={18}
                  strokeWidth={1.75}
                  className={current ? "text-accent-ink" : "text-faint"}
                />
                {labels[item.key]}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
