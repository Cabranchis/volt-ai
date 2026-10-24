# ADR 0011: Next.js native i18n and parameterised SQL (amends ADR 0007 and 0008)

Status: accepted (2026-10-24)

## Context
ADR 0007 chose `next-intl` and ADR 0008's plan mentioned Drizzle ORM. Both were chosen before reading the documentation bundled with Next.js 16.4, which now ships `cacheComponents`, `proxy.ts`, `next/root-params` and a documented dictionary-based i18n pattern.

## Decision
- **i18n**: use the native pattern. Routes live under `app/[lang]`, `generateStaticParams` returns `es` and `en`, dictionaries are typed JSON files, and `proxy.ts` redirects requests without a locale using `Accept-Language`. No i18n library.
- **Database access**: use the `postgres` driver with parameterised tagged-template queries, and validate every row with Zod before it reaches a component. The schema is defined once, in `db/migrations`.

## Consequences
- One dependency fewer, and no risk that a library lags behind `cacheComponents`.
- Translations are plain objects, so a missing key is a TypeScript error because both dictionaries are checked against the same type.
- Raw SQL is limited to a small repository module. Zod keeps the boundary typed and rejects malformed rows loudly.

## Rejected alternatives
- `next-intl`: well-built, but adds a dependency that must track a new rendering model.
- Drizzle: would define the schema a second time next to the SQL migrations.
