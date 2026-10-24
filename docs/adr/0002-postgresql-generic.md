# ADR 0002: PostgreSQL behind a generic DATABASE_URL

Status: accepted (2026-10-24)

## Context
The owner has Neon or Supabase available. Both are PostgreSQL with a free tier.

## Decision
Use plain PostgreSQL features only and read the connection string from `DATABASE_URL`. Schema lives in versioned SQL migrations in `db/migrations`. Local development and unit tests use SQLite through the same SQLAlchemy Core layer.

## Consequences
- Switching provider is a change of environment variable.
- Features specific to one provider (Supabase auth, Neon branching) are not used.
- The SQL used must stay portable between PostgreSQL and SQLite for the tests.

## Rejected alternatives
- MongoDB: data is tabular time series.
- SQLite in production: Vercel's filesystem is ephemeral.
