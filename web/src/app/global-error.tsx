"use client";

import { ERROR_TEXT } from "@/lib/i18n/errors";

/**
 * The last resort, when the layout itself failed. It replaces the whole document, so it has its own
 * html. It shows both languages: it cannot know the visitor's, and a language picked in the browser
 * would not match what the server rendered.
 */
export default function GlobalError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <html lang="es">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, padding: "2rem", maxWidth: "40rem" }}>
        <div role="alert">
          {(["es", "en"] as const).map((lang) => (
            <section key={lang} lang={lang} style={{ marginBottom: "1.5rem" }}>
              <h1 style={{ fontSize: "1.25rem" }}>{ERROR_TEXT[lang].title}</h1>
              <p>{ERROR_TEXT[lang].body}</p>
            </section>
          ))}
          <button type="button" onClick={retry} style={{ padding: "0.4rem 0.8rem" }}>
            {ERROR_TEXT.es.retry} / {ERROR_TEXT.en.retry}
          </button>
        </div>
      </body>
    </html>
  );
}
