import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { hasLocale, negotiateLocale } from "@/lib/i18n/config";

/** Redirect paths without a locale prefix (e.g. /price) to the visitor's language (e.g. /es/price). */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const first = pathname.split("/")[1] ?? "";
  if (hasLocale(first)) return NextResponse.next();

  const locale = negotiateLocale(request.headers.get("accept-language"));
  const url = request.nextUrl.clone();
  url.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(url);
}

export const config = {
  // Skip the API, Next internals and any file with an extension (icons, fonts, sitemap...).
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
