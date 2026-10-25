import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Brand } from "@/components/shell/Brand";
import { MobileNav } from "@/components/shell/MobileNav";
import { SidebarBody } from "@/components/shell/SidebarBody";
import { locales } from "@/lib/i18n/config";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";
import { SITE_URL } from "@/lib/site";
import "../globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

// Applies a saved theme before first paint so the page never flashes the wrong one.
const THEME_SCRIPT = `try{var t=localStorage.getItem('voltia-theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t)}catch(e){}`;

export function generateStaticParams() {
  return locales.map((lang) => ({ lang }));
}

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return {
    metadataBase: new URL(SITE_URL),
    title: { default: `${dict.app.name}: ${dict.app.tagline}`, template: `%s · ${dict.app.name}` },
    description: dict.app.description,
    applicationName: dict.app.name,
    openGraph: { siteName: dict.app.name, type: "website", description: dict.app.description },
  };
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f6f2" },
    { media: "(prefers-color-scheme: dark)", color: "#121316" },
  ],
};

export default async function RootLayout({ children }: LayoutProps<"/[lang]">) {
  const locale = await getLocale();
  const dict = await getDictionary();
  const brand = <Brand locale={locale} name={dict.app.name} />;

  return (
    <html
      lang={locale}
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-dvh text-ink antialiased">
        <a
          href="#main"
          className="sr-only rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50"
        >
          {dict.nav.skip}
        </a>
        <div className="mx-auto flex min-h-dvh max-w-[1520px]">
          <aside className="glass sticky top-3 m-3 mr-0 hidden h-[calc(100dvh-1.5rem)] w-60 shrink-0 flex-col gap-6 rounded-2xl p-4 lg:flex">
            {brand}
            <SidebarBody locale={locale} dict={dict} />
          </aside>
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="glass sticky top-0 z-30 flex items-center justify-between rounded-b-2xl px-4 py-3 lg:hidden">
              {brand}
              <MobileNav labels={dict.nav} brand={brand}>
                <SidebarBody locale={locale} dict={dict} />
              </MobileNav>
            </header>
            <main id="main" className="flex-1 px-4 py-8 sm:px-8 lg:px-12 lg:py-10">
              <div className="mx-auto w-full max-w-[1200px]">{children}</div>
            </main>
            <footer className="border-t border-line px-4 py-6 text-xs text-muted sm:px-8 lg:px-12">
              <p className="mx-auto max-w-[1200px] leading-relaxed">{dict.common.footer}</p>
            </footer>
          </div>
        </div>
      </body>
    </html>
  );
}
