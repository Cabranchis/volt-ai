import { Suspense } from "react";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { REPO_URL } from "@/lib/site";
import { DataSourceBadge } from "./DataSourceBadge";
import { LocaleSwitch } from "./LocaleSwitch";
import { NavLinks } from "./NavLinks";
import { ThemeSwitch } from "./ThemeSwitch";

/** Navigation plus the controls that belong with it. Shared by the sidebar and the mobile dialog. */
export function SidebarBody({ locale, dict }: { locale: Locale; dict: Dictionary }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col justify-between gap-8">
      <NavLinks locale={locale} labels={dict.nav} />
      <div className="flex flex-col gap-3">
        <Suspense fallback={<p className="skeleton h-4 w-32" aria-hidden="true" />}>
          <DataSourceBadge labels={dict.common} />
        </Suspense>
        <LocaleSwitch current={locale} label={dict.common.language} />
        <ThemeSwitch labels={dict.common} />
        {REPO_URL ? (
          <a
            href={REPO_URL}
            rel="noopener noreferrer"
            target="_blank"
            className="text-xs text-muted underline underline-offset-4 hover:text-ink"
          >
            {dict.common.github}
          </a>
        ) : null}
      </div>
    </div>
  );
}
