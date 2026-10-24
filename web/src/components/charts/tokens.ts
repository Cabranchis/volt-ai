/** Design tokens as the charts need them: resolved colours read from the CSS variables. */
export interface ChartTokens {
  surface: string;
  border: string;
  text: string;
  muted: string;
  faint: string;
  ref: string;
  demand: string;
  price: string;
  water: string;
  thermal: string;
  wind: string;
  solar: string;
  cogen: string;
  other: string;
  nino: string;
  nina: string;
  mid: string;
  font: string;
}

const read = (style: CSSStyleDeclaration, name: string, fallback: string): string =>
  style.getPropertyValue(name).trim() || fallback;

export function readTokens(): ChartTokens {
  const style = getComputedStyle(document.documentElement);
  return {
    surface: read(style, "--surface", "#fcfcfb"),
    border: read(style, "--border", "#dedcd5"),
    text: read(style, "--text", "#0b0b0b"),
    muted: read(style, "--text-muted", "#52514e"),
    faint: read(style, "--text-faint", "#6b6a65"),
    ref: read(style, "--c-ref", "#52514e"),
    demand: read(style, "--c-demand", "#6250d6"),
    price: read(style, "--c-price", "#eb6834"),
    water: read(style, "--c-water", "#2a78d6"),
    thermal: read(style, "--c-thermal", "#e34948"),
    wind: read(style, "--c-wind", "#1baf7a"),
    solar: read(style, "--c-solar", "#eda100"),
    cogen: read(style, "--c-cogen", "#e87ba4"),
    other: read(style, "--c-other", "#9a9990"),
    nino: read(style, "--c-nino", "#e34948"),
    nina: read(style, "--c-nina", "#2a78d6"),
    mid: read(style, "--c-mid", "#f0efec"),
    font: getComputedStyle(document.body).fontFamily,
  };
}

/** A colour with some opacity, from a #rrggbb token. */
export function withAlpha(hex: string, alpha: number): string {
  const value = hex.replace("#", "");
  if (value.length !== 6) return hex;
  const r = Number.parseInt(value.slice(0, 2), 16);
  const g = Number.parseInt(value.slice(2, 4), 16);
  const b = Number.parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
