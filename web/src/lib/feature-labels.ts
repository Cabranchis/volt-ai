import { z } from "zod";
import labelsJson from "./data/fixtures/feature-labels.json";
import type { Locale } from "./i18n/config";

const labels = z.record(z.string(), z.object({ es: z.string(), en: z.string() })).parse(labelsJson);

/** "reservoir_pct_lag7" to "Reservoir pct lag7": a readable fallback for a feature without a label. */
function humanise(key: string): string {
  const text = key.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Plain-language name of a model feature, from the pipeline's feature_labels.json. */
export function featureLabel(feature: string, locale: Locale): string {
  return labels[feature]?.[locale] ?? humanise(feature);
}
