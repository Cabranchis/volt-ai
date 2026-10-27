import { ImageResponse } from "next/og";
import { hasLocale } from "@/lib/i18n/config";
import { dictionaryFor } from "@/lib/i18n/dictionaries";

export const alt = "Volt-AI";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export function generateStaticParams() {
  return [{ lang: "es" }, { lang: "en" }];
}

const AMBER = "#f0b429";
const BOLT =
  "M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z";

/** The picture that link previews show (LinkedIn, WhatsApp, Slack): the brand, the promise and what the site covers. */
export default async function OpenGraphImage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  const dict = await dictionaryFor(hasLocale(lang) ? lang : "es");
  const topics = [dict.nav.demand, dict.nav.price, dict.nav.hydrology, dict.nav.analyst];

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px 80px",
          background: "linear-gradient(135deg, #121316 0%, #1b1d27 60%, #2a2147 100%)",
          color: "#f4f3ee",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
          <div
            style={{
              width: 104,
              height: 104,
              borderRadius: 26,
              background: AMBER,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="64" height="64" viewBox="0 0 24 24" fill="#1a1300">
              <path d={BOLT} />
            </svg>
          </div>
          <div style={{ fontSize: 96, fontWeight: 700, letterSpacing: -2, display: "flex" }}>
            <span>Volt-</span>
            <span style={{ color: AMBER }}>AI</span>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ fontSize: 60, fontWeight: 700, lineHeight: 1.1, letterSpacing: -1 }}>{dict.app.tagline}</div>
          <div style={{ fontSize: 30, lineHeight: 1.35, color: "#b9b8c4", maxWidth: 900 }}>
            {dict.business.description}
          </div>
        </div>

        <div style={{ display: "flex", gap: 14 }}>
          {topics.map((topic) => (
            <div
              key={topic}
              style={{
                fontSize: 26,
                padding: "10px 24px",
                borderRadius: 999,
                border: "2px solid rgba(240,180,41,0.55)",
                color: AMBER,
              }}
            >
              {topic}
            </div>
          ))}
        </div>
      </div>
    ),
    size,
  );
}
