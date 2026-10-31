# Deployment guide

Everything runs on free tiers. Four steps need you, because they involve your own accounts and secrets: creating the database, creating the repository, storing secrets and connecting Vercel. A Spanish version is in [deployment.es.md](deployment.es.md).

| Service | Used for | Cost | Notes |
| --- | --- | --- | --- |
| GitHub (public repository) | Source, CI, the daily pipeline | Free | Actions are free for public repositories |
| Neon or Supabase | PostgreSQL | Free tier | The app needs only about 10 to 20 MB (see below) |
| Vercel (Hobby) | The web app | Free for personal projects | Sign in with your GitHub account |
| Google AI Studio | Gemini key for the analyst | Free tier | Optional: without it the analyst answers from fixed summaries |

Provider limits change. Check the current free-tier limits of each service before relying on them. What Volt-AI uses, measured on the real data in October 2026:

- **Database size**: the complete history from 2018 (54 789 daily rows and 4 224 hourly rows) is a 5.6 MB SQLite file. PostgreSQL adds index overhead, so plan for 15 to 25 MB. The design target is below 500 MB (NFR-09).
- **Pipeline time**: a daily update takes about a minute. The first backfill takes about 10 minutes, mostly the generation-by-plant downloads.
- **Chat calls**: at most 12 questions per visitor per 10 minutes and 400 per day in total (`CHAT_DAILY_LIMIT`); beyond that the analyst answers without the model.

## 1. Create the database

**Neon**

1. Create a project named `voltia`. Choose the region closest to your Vercel region.
2. Copy the **pooled** connection string (the host contains `-pooler`). It looks like `postgresql://user:password@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require`. This is `DATABASE_URL`, used by the pipeline.

**Supabase**

1. Create a project named `voltia`.
2. Copy the connection string of the **transaction pooler** (port 6543). Replace `[YOUR-PASSWORD]`. This is `DATABASE_URL`.

Either way, `postgres://` and `postgresql://` URLs are both accepted; the pipeline rewrites them for the `psycopg` driver.

## 2. Load the schema and the history (from your computer)

```bash
cd pipeline
cp ../.env.example .env        # then edit DATABASE_URL
uv sync
uv run voltia migrate          # creates the tables and the voltia_ro role
uv run voltia backfill         # about 10 minutes, from 2018-01-01
uv run voltia train --predict  # backtest, final models, forecasts
uv run voltia anomalies
uv run voltia status           # every dataset should say status=ok
```

`.env` is ignored by git. Never commit it.

## 3. Give the web app its read-only role

The migration creates the role `voltia_ro` without a password and without login. In the provider's SQL editor run:

```sql
ALTER ROLE voltia_ro WITH LOGIN PASSWORD '<a long random password>';
```

Build a second connection string with that role. This is `DATABASE_URL_READONLY`. The role can read every table and write only `rate_limits` (the chat limiter). To check it, connect with it and run `INSERT INTO series_daily VALUES ('x', '2026-01-01', 1)`. It must fail with a permission error.

## 4. Create the repository and store the secrets

```bash
gh repo create voltia --public --source . --remote origin --push
gh secret set DATABASE_URL            # paste the pipeline connection string
gh secret set GOOGLE_GENERATIVE_AI_API_KEY   # optional
```

## 5. Deploy on Vercel

1. In Vercel choose **Add New, Project** and import the `voltia` repository.
2. Set **Root Directory** to `web`. Vercel detects Next.js. Under Settings, General, choose **Node.js 22.x**.
3. Add these environment variables (Production and Preview unless noted):

| Variable | Value | Required |
| --- | --- | --- |
| `DATABASE_URL_READONLY` | the read-only connection string from step 3 | Production |
| `GOOGLE_GENERATIVE_AI_API_KEY` | key from Google AI Studio | No |
| `GEMINI_MODEL` | defaults to `gemini-flash-latest` | No |
| `NEXT_PUBLIC_SITE_URL` | your production URL, e.g. `https://voltia.vercel.app` | Yes |
| `NEXT_PUBLIC_REPO_URL` | `https://github.com/<you>/voltia` | No (hides the link if empty) |
| `RATE_LIMIT_SALT` | a random string | Recommended |
| `CHAT_DAILY_LIMIT` | `400` | No |

Leave `DATABASE_URL_READONLY` out of **Preview** so pull-request previews use the saved snapshot and never touch the database.

4. Deploy. The build reads the database while prerendering, so the database must be reachable at build time.

## 6. Check it works

- `https://<your-site>/api/v1/health` returns `"source": "postgres"` and a recent `lastDay` for each series.
- The page footer of the sidebar says **Live database**, not **Demo snapshot**.
- In GitHub, **Actions, Daily pipeline, Run workflow** finishes green.
- The analyst answers a question. With a Gemini key it shows the lookups it made; without one it shows the notice that the model is not configured.

## 7. Data refresh

The pipeline workflow runs every day at 06:30 and 17:30 Colombia time. XM publishes each day at no fixed hour, so a second workflow, `Watch XM for a new day` (`poll.yml`), runs every hour at minute 17, asks XM whether a complete day exists that the latest model run has not used (`voltia check`) and, only then, starts `Daily pipeline`. A new XM day is therefore ingested and trained on within about one to two hours (GitHub can delay a scheduled run). When the run ends, its last step asks the site to drop its cached reads (`POST /api/revalidate`), so a new forecast appears as soon as the run finishes. The pages still revalidate every hour as a fallback.

The same random value, `REVALIDATE_TOKEN`, must be set in two places: as a GitHub Actions secret and as a sensitive Vercel environment variable (Production and Preview). Without the secret the step only warns. Optionally set the repository variable `SITE_URL` if the domain changes.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Build fails with a connection error | `DATABASE_URL_READONLY` is wrong or the role has no login. Repeat step 3. |
| Build fails on `permission denied` | The role was created before the tables existed. Run `GRANT SELECT ON ALL TABLES IN SCHEMA public TO voltia_ro;`. |
| The site says **Demo snapshot** in production | `DATABASE_URL_READONLY` is not set for the Production environment. |
| The pipeline fails with `prepared statement` errors | You used the direct connection with a pooler in front, or the opposite. Use the pooled string. |
| The analyst never uses the model | The key is missing or its daily quota is spent. The notice appears in the chat. |
