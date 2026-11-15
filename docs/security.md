# Security

A one-page threat model: what is worth protecting, where it can be attacked and which control stops each attack. Reporting a problem is covered in [SECURITY.md](../SECURITY.md).

## What there is to protect

| Asset | Why it matters | Where it lives |
| --- | --- | --- |
| Write-capable database URL (`DATABASE_URL`) | Whoever has it can alter or delete the data | GitHub Actions secret, `pipeline/.env` (ignored) |
| Read-only database URL (`DATABASE_URL_READONLY`) | Reads data that is already public; may write only `rate_limits` | Vercel environment |
| Gemini key | Spending quota on the owner's account | GitHub secret and Vercel environment |
| The live track record (`forecast_log`) | It is the evidence the forecasts are worth trusting, and it cannot be rebuilt | Neon, plus the weekly backup |
| Visitors | The site collects nothing: no accounts, no cookies, no stored messages. Only a salted hash of the address is kept for rate limiting | `rate_limits` |

The market data are public, so confidentiality of the data itself is not a goal; integrity and availability are.

## Where it can be attacked, and what stops it

| Surface | Threat | Control | Where |
| --- | --- | --- | --- |
| Web pages | Script injection | Strict CSP (no remote origins, `object-src 'none'`, `frame-ancestors 'none'`); no HTML is rendered from users or from the model; the one `dangerouslySetInnerHTML` is a fixed theme script | `web/next.config.ts` |
| Web pages | Clickjacking, MIME sniffing, cross-origin window access, downgrade | `X-Frame-Options`, `nosniff`, `Cross-Origin-Opener-Policy`, HSTS, `upgrade-insecure-requests` (production) | `web/next.config.ts`, checked in `web/e2e/site.spec.ts` |
| REST API | SQL injection | Every query uses parameterised templates; series names come from an allow-list validated with Zod | `web/src/lib/data/postgres.ts`, `web/src/app/api/v1/*` |
| REST API | Load that bypasses the CDN cache | Per-client limit of 60 requests a minute on the endpoints with free arguments and 120 on the rest; unknown query parameters are refused, series are sorted and the range clamped to the history so equivalent requests share one cached read; at most 8 series and a 4000-day range; five-minute CDN cache | `web/src/lib/api.ts`, `web/src/app/api/v1/series/route.ts` |
| REST API, pages | Data from the snapshot, or an error page, mistaken for live data | `X-Data-Source` on every API response (errors included); production serving the snapshot makes health `degraded`; a page that cannot read its data shows "data unavailable" and no numbers | `web/src/lib/data/repository.ts`, `web/src/app/[lang]/error.tsx` |
| Database | A web bug turning into a data change | The web role cannot write (only `rate_limits`); queries over 5 s are cancelled | `db/migrations/0002_roles.pg.sql`, `0006_ro_timeouts.pg.sql` |
| Chat | Cost abuse, prompt injection, data exfiltration | Origin check, 16 KB body cap read as a stream (never in full), schema-validated messages, 12 questions per 10 minutes per client (IPv6 by /64), an hourly and a daily global cap, and fixed summaries instead of the model when a cap is reached or the limiter is down; the model can only call typed tools, never SQL; provider errors are not sent to the browser | `web/src/app/api/chat/route.ts`, `web/src/lib/ai/` |
| Data | A wrong or half-published value, or a bad forecast, reaching a person who decides with it | Step guards on every price, market, contract and generation series, compared also with the last stored value; floors above zero; required series per batch; days after the requested range rejected; a publication gate that refuses a forecast that is not finite, ordered, near recent history, better than the naive and calibrated. A refused run stores nothing and the site keeps the previous forecast | `pipeline/src/voltia/ingest.py`, `schemas.py`, `gates.py`, ADR 0013 and 0014 |
| Data | Data or a forecast that is old without anyone noticing | `/api/v1/health` is `ok`, `stale` or `degraded` by the age of the data, the model and the forecast; the pages show when the forecast was issued; a daily watchdog opens an issue and an outside monitor reads the same endpoint | `web/src/lib/health.ts`, `.github/workflows/watchdog.yml`, runbook |
| Rate limiting | Reversing a stored hash back to an address | The salt is `RATE_LIMIT_SALT` or, if missing, the read-only database URL, never a value in the repository | `web/src/lib/ai/ratelimit.ts` |
| CSV downloads | Formula injection in a spreadsheet | Cells that begin with `= + - @` are neutralised | `web/src/lib/api.ts` |
| Supply chain | A vulnerable or tampered dependency or action | Lockfiles with `--frozen` / `npm ci`; actions pinned by commit; `npm audit` and `pip-audit` in CI; Dependabot; CodeQL; gitleaks over the whole history in CI (report-only until it has run clean) | `.github/workflows/`, `.github/dependabot.yml` |
| Workflows | A secret leaking through a step | `contents: read` by default (`actions: write` in the watcher, `issues: write` in the watchdog, `security-events: write` in CodeQL, each only where it is needed); `persist-credentials: false`; the write URL is passed only to the steps that need it; manual inputs are typed choices used only as environment values | `.github/workflows/pipeline.yml`, `watchdog.yml` |
| Cache refresh endpoint | Anyone forcing reloads of the database, or guessing the token | `POST /api/revalidate` needs `Authorization: Bearer REVALIDATE_TOKEN` (compared in constant time over SHA-256 digests), answers 503 when no token is configured, is rate limited per client, and can only expire cached reads, never write or read data | `web/src/app/api/revalidate/route.ts` |
| Watcher workflow | A token that can start workflows being misused | `poll.yml` has `actions: write` and nothing more; it only starts `pipeline.yml` and never runs code from a pull request. Its one step with a secret is `voltia check`, which only reads (no migration, one `SELECT`) but today receives the same write-capable `DATABASE_URL` as the pipeline: giving it the read-only role would need a second GitHub secret, and the trade-off is accepted for now | `.github/workflows/poll.yml` |
| Repository | A secret committed by mistake; the branch rewritten or deleted | Secret scanning with push protection; a ruleset blocks force-push and deletion of `main`; history checked for secrets | GitHub settings |
| Data loss | The database lost or corrupted | Weekly export of the tables that cannot be rebuilt (artifact kept 90 days); the rest is rebuilt with `voltia backfill` | `.github/workflows/backup.yml`, `voltia archive` |

## Accepted risks

- **The chat's hourly cap can be used up on purpose.** A few networks at 12 questions per 10 minutes each reach the 60 of the hour and keep everyone on the fixed summaries until the hour ends. That costs nothing and is the fail-open choice: the quota the language model spends is bounded, and the summaries still answer.
- **The client address is read from `x-forwarded-for`.** Vercel overwrites that header, so on Vercel a client cannot choose its key. Behind another proxy, or self-hosted without one, it could; keep the deployment on Vercel or put a proxy that sets the header in front of it.

- **`script-src 'unsafe-inline'`.** Next.js emits inline bootstrap scripts whose content changes per page, so hashes cannot be listed ahead of time, and a nonce would force every page to render dynamically (ADR 0010). The exposure is small because nothing a visitor or the model writes is ever rendered as HTML.
- **No account system.** There is nothing to take over, which also means the rate limits are per address and a determined attacker with many addresses can still spend the daily chat quota; the chat then falls back to fixed summaries.
- **Public data.** An exported backup is public data plus model metrics; it carries no personal data.

## Operating it

- Rotating secrets is in the [runbook](runbook.md). Rotating `DATABASE_URL_READONLY` changes the rate-limit salt if `RATE_LIMIT_SALT` is not set, which only resets the counters.
- **Recommended and not automated:** set `RATE_LIMIT_SALT` in Vercel to a random string, so the salt does not depend on the database URL.
- Restoring the backup is in the [runbook](runbook.md#restoring-the-backup).
