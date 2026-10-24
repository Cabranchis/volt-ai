# Design system

VoltIA is an **operate** surface: people come to read numbers, compare a forecast with what happened and ask a question. The interface should disappear into that task. Familiar structure (sidebar, header, panels), one type family, restrained colour, and charts that are the loudest thing on the page.

## Principles

1. **Data is the loudest thing.** Chrome is neutral. Colour is spent on series and on one accent for the current selection and primary actions.
2. **Color follows the entity, never its rank.** Demand is always violet, price orange, water blue, thermal red. A filter never repaints the survivors.
3. **Every chart has a text equivalent.** A summary sentence and a data table sit next to it, for screen readers, for colour-blind readers and for anyone who wants the numbers.
4. **Honest about uncertainty.** Forecasts always show their band. Stale data is labelled, never shown as current.
5. **Two languages are first-class.** Layouts leave room for Spanish text (about 20 % longer than English).

## Typography

One family, **Geist Sans**, for headings, labels, body and data. Geist Mono only for code in the analyst chat. Fixed rem scale (ratio about 1.2), no fluid sizes.

| Token | Size | Use |
| --- | --- | --- |
| `--text-xs` | 0.75rem | axis ticks, captions, table meta |
| `--text-sm` | 0.875rem | table cells, secondary text, controls |
| `--text-base` | 1rem | body, prose (measure 65 to 75 characters) |
| `--text-lg` | 1.25rem | panel titles |
| `--text-xl` | 1.5rem | page titles |
| `--text-2xl` | 2rem | the single headline figure of a page |

Large single numbers use proportional figures. Columns of numbers (tables, axes) use tabular figures.

## Colour tokens

Neutrals are slightly warm in light mode and slightly cool in dark mode. The accent (a warm "volt" amber) marks the current navigation item, primary buttons and focus rings. It is never used for data.

| Role | Light | Dark |
| --- | --- | --- |
| `--bg` | `#f7f6f2` | `#121316` |
| `--surface` | `#fcfcfb` | `#1a1a19` |
| `--surface-2` (sidebar, toolbars) | `#f0efec` | `#17171a` |
| `--border` | `#dedcd5` | `#2c2c30` |
| `--text` | `#0b0b0b` | `#f0efec` |
| `--text-muted` | `#52514e` | `#c3c2b7` |
| `--text-faint` | `#6b6a65` | `#9a9990` |
| `--accent` | `#e2a400` | `#f0b429` |
| `--accent-text` | `#7a5600` | `#f0b429` |
| `--focus` | `#2a78d6` | `#6da7ec` |

Chart surface equals `--surface`. Text on charts always uses text tokens, never the series colour.

## Data colours (validated)

Palette from the data-viz reference instance, assigned by entity and **validated with the palette script on the exact sequences used**.

| Entity | Light | Dark | Used for |
| --- | --- | --- | --- |
| Demand | `#6250d6` | `#9085e9` | demand series and forecast |
| Price | `#eb6834` | `#d95926` | spot price series and forecast |
| Water (reservoirs, inflows, hydro generation) | `#2a78d6` | `#3987e5` | hydrology page, hydro in the mix |
| Thermal generation | `#e34948` | `#e66767` | mix |
| Wind | `#1baf7a` | `#199e70` | mix |
| Solar | `#eda100` | `#c98500` | mix |
| Cogeneration | `#e87ba4` | `#d55181` | mix |
| Other | `#9a9990` | `#6b6a65` | mix remainder (neutral, not categorical) |
| Reference line (historical mean, last observed day) | `#52514e` | `#c3c2b7` | dashed or thin rules |
| El Niño / La Niña (diverging) | `#e34948` / `#2a78d6` | `#e66767` / `#3987e5` | ONI bars, neutral midpoint `#f0efec` / `#383835` |

Validation results (see the script output in the development log):

- **Mix stack order, bottom to top: thermal, hydro, wind, solar, cogeneration, other.** Light: lightness, chroma, adjacent colour-vision separation (9.1 ΔE) and normal-vision floor (19.6 ΔE) pass. Dark: all five checks pass, including contrast (8.4 ΔE worst adjacent).
- Only 4 of the 120 possible orderings of those five hues pass every gate in both modes. The order above is one of them. An earlier order (hydro, thermal, wind, ...) placed red next to aqua and failed the colour-vision gate at 6.9 ΔE, so it was rejected.
- Demand, price and water are never stacked together; the three of them pass with 24.7 ΔE (light) and 26.0 ΔE (dark) worst case.
- In light mode wind, solar and cogeneration sit below 3:1 contrast on the surface. The documented relief applies: always-visible legend, tooltip with the value, 2 px surface gap between segments and a data table next to each chart.

## Marks

Lines 2 px with round joins. Area washes at about 10 % opacity. Forecast band: the series colour at 14 % opacity, P50 line solid, last observed point marked. Grid lines hairline and recessive, none on the x axis. Markers at least 8 px with a 2 px ring in the surface colour. 2 px gaps between stacked segments. Anomalies use **shape**, not colour: a triangle up for a high day and down for a low day, drawn in the text colour.

## Layout

- App shell: fixed sidebar (240 px) on wide screens, top bar with a menu button below 960 px. Content max width 1200 px.
- Page header: title, one-sentence description, freshness badge on the right.
- Panels have a 1 px border and no shadow (elevation is declared once, by the border). Radius 12 px.
- Headline figures are laid out as a single ruled strip, not as a row of identical cards.
- Spacing scale 4, 8, 12, 16, 24, 32, 48. More space above a heading than below it.

## Components

AppShell, SideNav, TopBar (language switch, theme switch), PageHeader, FreshnessBadge, Panel, StatStrip, ChartFrame (title, summary, range control, skeleton, error, empty), ForecastChart, TimeSeriesChart, MixChart, DriversChart, RangeControl (segmented), DataTable, AnomalyList, MetricsTable, ChatPanel (messages, suggestions, composer, tool activity), Skeleton, EmptyState.

Every interactive component defines default, hover, focus-visible, active, disabled, loading and error states. Focus rings use `--focus`. Browser defaults that carry design (selection colour, caret, scrollbars, numerals) are themed from the tokens.

## Motion

150 to 250 ms for state changes. One authored moment: the first paint of a forecast band reveals left to right once. Everything respects `prefers-reduced-motion`.

## Accessibility

WCAG 2.2 AA. Text contrast at least 4.5:1, large text 3:1. Full keyboard navigation, visible focus, skip link, landmarks, `lang` on the document, language switch with `hreflang` alternates. Charts expose a summary and a table; status is never colour alone.
