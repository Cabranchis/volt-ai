# ADR 0006: AI analyst through typed tools, never free-form SQL

Status: accepted (2026-10-24)

## Context
Visitors ask questions in natural language. Letting a model write SQL against the database would expose the data to prompt injection and expensive queries.

## Decision
Use Gemini Flash through the Vercel AI SDK. The model may only call a fixed set of tools, each with a zod schema that bounds dates, series names and result size. The tools call the same repository functions as the REST API, using the read-only database role. The system prompt requires citing figures and dates.

## Consequences
- The attack surface is the tool list and its schemas, which are unit tested.
- Questions that need data not covered by a tool get an honest "I cannot answer that".
- Without an API key the endpoint answers with deterministic summaries (FR-12).

## Rejected alternatives
- Text-to-SQL: injection and cost risk.
- Local models (Ollama): not available when deployed.
