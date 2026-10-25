"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { locales, switchLocalePath, type Locale } from "@/lib/i18n/config";

const NAMES: Record<Locale, string> = { es: "Español", en: "English" };

export function LocaleSwitch({ current, label }: { current: Locale; label: string }) {
  const pathname = usePathname();

  return (
    <nav aria-label={label}>
      <ul className="flex rounded-lg border border-line bg-surface p-0.5">
        {locales.map((locale) => (
          <li key={locale} className="flex-1">
            <Link
              href={switchLocalePath(pathname, locale)}
              hrefLang={locale}
              lang={locale}
              aria-current={locale === current ? "true" : undefined}
              title={NAMES[locale]}
              className={[
                "grid h-9 place-items-center rounded-md text-xs font-semibold tracking-wide",
                locale === current ? "bg-accent text-on-accent" : "text-muted hover:text-ink",
              ].join(" ")}
            >
              {locale.toUpperCase()}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
