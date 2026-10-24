# ADR 0008: Single repository, data access behind an interface

Status: accepted (2026-10-24)

## Context
The project has a Python pipeline and a TypeScript web app that share one database schema. It is also a portfolio piece that people read in a few minutes.

## Decision
One repository with `pipeline/`, `web/`, `db/` and `docs/`. The web app reads data through a `Repository` interface with two implementations: PostgreSQL and JSON fixtures.

## Consequences
- One link for reviewers, one CI, one history.
- Unit tests, end-to-end tests and pull-request previews run without a database or secrets.
- The fixtures must be kept in step with the schema. A contract test loads them through the same zod schemas used for database rows.

## Rejected alternatives
- Two repositories: harder to review and to keep in sync.
- Mocks inside each test: duplicated and drift-prone.
