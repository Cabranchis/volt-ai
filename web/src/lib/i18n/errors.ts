/**
 * The text of the error screens. They are client components that render when a page could not be
 * built (the database is down, a read timed out), possibly outside the layout that loads the
 * dictionaries, so they keep their two short texts here instead of importing both full dictionaries.
 */
export type ErrorLocale = "es" | "en";

export const ERROR_TEXT: Record<ErrorLocale, { title: string; body: string; retry: string }> = {
  es: {
    title: "Datos no disponibles por ahora",
    body: "No se pudieron leer los datos. No se muestra nada en su lugar, para no mostrar cifras que no son las reales. Vuelve a intentarlo en unos minutos.",
    retry: "Reintentar",
  },
  en: {
    title: "Data is unavailable right now",
    body: "The data could not be read. Nothing is shown in its place, so that no figure that is not the real one appears. Try again in a few minutes.",
    retry: "Try again",
  },
};

export const errorLocale = (lang: string | undefined | null): ErrorLocale => (lang === "en" ? "en" : "es");
