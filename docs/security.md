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
| REST API | Load that bypasses the CDN cache | Per-client limit of 60 requests a minute on the endpoints with free arguments; a 4000-day range cap | `web/src/lib/api.ts` |
| Database | A web bug turning into a data change | The web role cannot write (only `rate_limits`); queries over 5 s are cancelled | `db/migrations/0002_roles.pg.sql`, `0006_ro_timeouts.pg.sql` |
| Chat | Cost abuse, prompt injection, data exfiltration | Origin check, 16 KB body cap, schema-validated messages, 12 questions per 10 minutes per client and a daily global cap; the model can only call typed tools, never SQL; provider errors are not sent to the browser | `web/src/app/api/chat/route.ts`, `web/src/lib/ai/` |
| Rate limiting | Reversing a stored hash back to an address | The salt is `RATE_LIMIT_SALT` or, if missing, the read-only database URL, never a value in the repository | `web/src/lib/ai/ratelimit.ts` |
| CSV downloads | Formula injection in a spreadsheet | Cells that begin with `= + - @` are neutralised | `web/src/lib/api.ts` |
| Supply chain | A vulnerable or tampered dependency or action | Lockfiles with `--frozen` / `npm ci`; actions pinned by commit; `npm audit` and `pip-audit` in CI; Dependabot; CodeQL | `.github/workflows/`, `.github/dependabot.yml` |
| Workflows | A secret leaking through a step | `contents: read` only; `persist-credentials: false`; the write URL is passed only to the steps that need it | `.github/workflows/pipeline.yml` |
| Watcher workflow | A token that can start workflows being misused | `poll.yml` has `actions: write` and nothing more; it only starts `pipeline.yml` and never runs code from a pull request. Its one step with a secret is `voltia check`, which only reads (no migration, one `SELECT`) but today receives the same write-capable `DATABASE_URL` as the pipeline: giving it the read-only role would need a second GitHub secret, and the trade-off is accepted for now | `.github/workflows/poll.yml` |
| Repository | A secret committed by mistake; the branch rewritten or deleted | Secret scanning with push protection; a ruleset blocks force-push and deletion of `main`; history checked for secrets | GitHub settings |
| Data loss | The database lost or corrupted | Weekly export of the tables that cannot be rebuilt (artifact kept 90 days); the rest is rebuilt with `voltia backfill` | `.github/workflows/backup.yml`, `voltia archive` |

## Accepted risks

- **`script-src 'unsafe-inline'`.** Next.js emits inline bootstrap scripts whose content changes per page, so hashes cannot be listed ahead of time, and a nonce would force every page to render dynamically (ADR 0010). The exposure is small because nothing a visitor or the model writes is ever rendered as HTML.
- **No account system.** There is nothing to take over, which also means the rate limits are per address and a determined attacker with many addresses can still spend the daily chat quota; the chat then falls back to fixed summaries.
- **Public data.** An exported backup is public data plus model metrics; it carries no personal data.

## Operating it

- Rotating secrets is in the [runbook](runbook.md). Rotating `DATABASE_URL_READONLY` changes the rate-limit salt if `RATE_LIMIT_SALT` is not set, which only resets the counters.
- **Recommended and not automated:** set `RATE_LIMIT_SALT` in Vercel to a random string, so the salt does not depend on the database URL.
- Restoring the backup is in the [runbook](runbook.md#restoring-the-backup).
