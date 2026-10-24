import type { Locale } from "./i18n/config";

/** Set NEXT_PUBLIC_REPO_URL when the repository is public; the link is hidden otherwise. */
export const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL || null;

export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";

export interface NavItem {
  key: "overview" | "demand" | "price" | "hydrology" | "anomalies" | "models" | "analyst" | "about";
  path: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { key: "overview", path: "" },
  { key: "demand", path: "/demand" },
  { key: "price", path: "/price" },
  { key: "hydrology", path: "/hydrology" },
  { key: "anomalies", path: "/anomalies" },
  { key: "models", path: "/models" },
  { key: "analyst", path: "/analyst" },
  { key: "about", path: "/about" },
];

export const hrefFor = (locale: Locale, path: string): string => `/${locale}${path}`;
