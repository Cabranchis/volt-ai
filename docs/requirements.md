# Requirements

VoltIA turns the public data of Colombia's electricity market (XM) into forecasts, anomaly detection and an AI analyst. This document is the source of truth for scope. Every requirement has an ID that tests and pull requests can reference.

## 1. Actors

| Actor | Goal |
| --- | --- |
| Visitor (analyst, student, recruiter) | Understand the state of the Colombian power system today and where it is heading. |
| Developer | Consume the data and forecasts through a documented REST API. |
| Maintainer | Keep the pipeline healthy and know when data is stale. |

## 2. Use cases

| ID | Use case | Main flow | Success criteria |
| --- | --- | --- | --- |
| UC-01 | Overview | Visitor opens the home page and sees today's KPIs: demand, spot price, reservoir level, ONI index and generation mix, each with change versus last week and last year. | KPIs load without client-side fetching and show the date of the underlying data. |
| UC-02 | Demand forecast | Visitor opens *Demand*, sees 30 daily forecasts with P10/P50/P90 bands next to history, and the model's historical error. | Bands, last actuals and backtest error are on one chart. |
| UC-03 | Price forecast | Visitor opens *Price*, sees a 14-day spot price forecast with bands and the top drivers (SHAP) of the latest forecast. | Drivers are named in plain language, in both languages. |
| UC-04 | Hydrology and El Niño | Visitor sees reservoir volume, inflows versus the historical mean and the ONI series, and how they relate to price. | Chart overlays at least inflows, reservoir % and price. |
| UC-05 | Anomalies | Visitor browses atypical days for demand and price with a severity score and a short explanation. | Known events (2020 lockdown, 2023-24 El Niño) appear in the list. |
| UC-06 | AI analyst | Visitor asks a question in natural language and gets an answer backed by data the model fetched through typed tools. | The answer cites the figures and dates it used. No free-form SQL is ever executed. |
| UC-07 | Daily briefing | The pipeline writes an executive summary in ES and EN once per day. | Page views cost zero model calls. |
| UC-08 | Model transparency | Visitor reads the model card: data, method, backtest metrics versus baselines, last training date, limitations. | Metrics are the real ones from the last run, including when the model does not beat the baseline. |
| UC-09 | Public API | Developer calls `/api/v1/*` and reads the OpenAPI spec. | Read-only, versioned, documented, and cached at the CDN, with a per-client limit (60 requests a minute) on `series` and `anomalies`. |
| UC-10 | Operations | Maintainer sees whether the daily pipeline ran. If it failed, the dashboard says so. | `/api/v1/health` reports freshness per dataset. |

## 3. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-01 | The pipeline ingests from XM: national demand (`DemaSIN`), spot price (`PrecBolsNaci`), generation for the system and by resource (`Gene`), inflows (`AporEner`, `PorcApor`, `AporEnerMediHist`) and reservoir volume (`PorcVoluUtilDiar`, `VoluUtilDiarEner`). `DemaReal` is not used: for the system entity it covers only part of the load (57 GWh/day against 248 GWh/day for `DemaSIN`). |
| FR-02 | The pipeline ingests exogenous data: daily weather for Bogotá, Medellín, Cali and Barranquilla (Open-Meteo), the NOAA ONI index, and Colombian public holidays. |
| FR-03 | Every ingested batch is validated against a schema (types, plausible ranges, duplicates, gaps of more than 3 consecutive days) before it is stored. Invalid batches are rejected and reported, never partly stored. Days that XM has not finished settling are held back, not stored: hourly days need all 24 hours, and a demand day must reconcile with that day's total generation (see ADR 0009). |
| FR-04 | Loading is idempotent: running the same day twice produces the same database. |
| FR-05 | The backfill covers 2018-01-01 to today, respecting XM's 31-day window per request. |
| FR-06 | Demand is forecast 30 days ahead and spot price 14 days ahead, as P10, P50 and P90. |
| FR-07 | Every model is backtested with rolling-origin evaluation against a seasonal-naive baseline and an ETS baseline. Metrics: MAPE, sMAPE, MASE, interval coverage. |
| FR-08 | Each forecast stores the top feature contributions (SHAP) for explanation. |
| FR-09 | Anomalies are detected on demand and price using STL residuals and Isolation Forest, with a severity score. |
| FR-10 | The web app is bilingual (ES/EN) with a language switch and localized URLs. |
| FR-11 | The AI analyst can only call a fixed set of typed tools (series, forecast, anomalies, hydrology, compare periods). Arguments are validated. |
| FR-12 | Without a Gemini key, the analyst answers with deterministic summaries and the briefing uses a template. The app is fully usable. |
| FR-13 | The REST API exposes series, forecasts, anomalies, model metrics and health, with an OpenAPI document. |

## 4. Non-functional requirements

| ID | Requirement | How it is checked |
| --- | --- | --- |
| NFR-01 | Cost is zero: free tiers only, no card required. | Deployment guide lists each service and its free limit. |
| NFR-02 | Largest Contentful Paint under 2.5 s on a mid-range mobile profile. | Lighthouse in the verification phase. |
| NFR-03 | Accessibility WCAG 2.2 AA, light and dark themes, keyboard navigable, charts with text alternatives. | Lighthouse and axe in Playwright. |
| NFR-04 | The web app connects with a database role that can only read the data tables. Its single write permission is on `rate_limits`, which the chat limiter needs. | Test that a write to a data table with that role fails. |
| NFR-05 | Strict security headers (CSP, frame, referrer, permissions policies). No secret in the repository. | Header test and secret scan before every commit. |
| NFR-06 | The chat endpoint is rate limited per client and caps input size and tool calls per request. | Unit test of the limiter and of the tool argument schemas. |
| NFR-07 | Reproducible builds: lockfiles for Python and Node, pinned CI actions. | CI installs from lockfiles only. |
| NFR-08 | Pipeline coverage of at least 80 % with no network in tests. | CI coverage gate. |
| NFR-09 | Database stays below 0.5 GB. | Size check in the runbook. |
| NFR-10 | Data freshness is visible to users. Stale data is labelled, never silently shown as current. | Health endpoint and UI banner. |

## 5. Out of scope

- Real-time (sub-hourly) data and market bidding advice.
- User accounts and personalisation.
- Any claim that forecasts are suitable for trading. The model card states the limits.

## 6. Data sources and terms

| Source | Use | Access |
| --- | --- | --- |
| XM public API (`servapibi.xm.com.co`) | Market and system data | Open, no key |
| Open-Meteo archive and forecast API | Weather | Open, no key, non-commercial free tier |
| NOAA CPC ONI | El Niño index | Open |
| `holidays` Python package | Colombian public holidays | Open source |
| Google Gemini (optional) | AI analyst and briefing | Free API key |
