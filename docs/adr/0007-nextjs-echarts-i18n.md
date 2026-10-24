# ADR 0007: Next.js, Tailwind, ECharts and next-intl

Status: accepted (2026-10-24)

## Context
The front end must look like a product, be bilingual, draw forecast bands over years of daily data, and deploy free on Vercel.

## Decision
Next.js (App Router, TypeScript) with incremental static regeneration, Tailwind CSS for styling, Apache ECharts for charts and next-intl for `/es` and `/en` routes.

## Consequences
- Pages are pre-rendered and revalidated hourly, so database load is tiny.
- ECharts handles thousands of points and confidence bands without custom code.
- Chart components are client-side and must ship text alternatives for accessibility.

## Rejected alternatives
- Streamlit or Dash: faster to write, but read as prototypes and cannot be styled to portfolio quality.
- Recharts: weaker with long series and shaded bands.
