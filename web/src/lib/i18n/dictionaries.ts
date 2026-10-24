import { lang } from "next/root-params";
import { notFound } from "next/navigation";
import { hasLocale, type Locale } from "./config";
import type { Dictionary } from "./en";

const dictionaries: Record<Locale, () => Promise<Dictionary>> = {
  es: () => import("./es").then((m) => m.es),
  en: () => import("./en").then((m) => m.en),
};

/** The current request's locale, from the [lang] root parameter. */
export async function getLocale(): Promise<Locale> {
  const value = await lang();
  if (!hasLocale(value)) notFound();
  return value;
}

export async function getDictionary(): Promise<Dictionary> {
  return dictionaries[await getLocale()]();
}

/** Dictionary for an explicit locale, for code that already knows it (route handlers, tests). */
export function dictionaryFor(locale: Locale): Promise<Dictionary> {
  return dictionaries[locale]();
}
