import { FORECAST_TARGETS, SERIES_NAMES } from "./data/types";

const date = { type: "string", pattern: "^\\d{4}-\\d{2}-\\d{2}$", example: "2026-10-21" };
const problemResponse = (description: string) => ({
  description,
  content: {
    "application/problem+json": { schema: { $ref: "#/components/schemas/Problem" } },
  },
});

/** OpenAPI 3.1 description of the public, read-only API. Kept next to the handlers it describes. */
export const openApiDocument = {
  openapi: "3.1.0",
  info: {
    title: "VoltIA API",
    version: "1.0.0",
    description:
      "Read-only access to Colombian power-system series, forecasts and anomalies built from XM open data. Responses are cached for an hour.",
    license: { name: "MIT", identifier: "MIT" },
  },
  servers: [{ url: "/api/v1" }],
  paths: {
    "/series": {
      get: {
        summary: "Daily series",
        description: "Values are returned in columns: one shared `dates` array and one array per series (null where missing).",
        parameters: [
          {
            name: "names",
            in: "query",
            required: true,
            description: "Comma-separated series names.",
            schema: { type: "string", example: "demand_kwh,price_mean_cop_kwh" },
          },
          { name: "from", in: "query", schema: date },
          { name: "to", in: "query", schema: date },
        ],
        responses: {
          "200": {
            description: "Series data",
            content: { "application/json": { schema: { $ref: "#/components/schemas/SeriesFrame" } } },
          },
          "400": problemResponse("Invalid parameters"),
        },
      },
    },
    "/forecasts/{target}": {
      get: {
        summary: "Latest forecast",
        description: "P10, P50 and P90 per day from the latest training run, with the main drivers of each day.",
        parameters: [{ name: "target", in: "path", required: true, schema: { type: "string", enum: ["demand", "price"] } }],
        responses: {
          "200": {
            description: "Forecast",
            content: { "application/json": { schema: { $ref: "#/components/schemas/Forecast" } } },
          },
          "404": problemResponse("Unknown target or no forecast yet"),
        },
      },
    },
    "/anomalies": {
      get: {
        summary: "Unusual days",
        parameters: [
          { name: "target", in: "query", schema: { type: "string", enum: [...FORECAST_TARGETS] } },
          { name: "limit", in: "query", schema: { type: "integer", minimum: 1, maximum: 200, default: 50 } },
        ],
        responses: {
          "200": {
            description: "Anomalies, most severe first",
            content: { "application/json": { schema: { type: "array", items: { $ref: "#/components/schemas/Anomaly" } } } },
          },
          "400": problemResponse("Invalid parameters"),
        },
      },
    },
    "/model": {
      get: {
        summary: "Latest training run",
        description: "Backtest metrics of the model and its baselines, training dates and parameters.",
        responses: {
          "200": { description: "Training run", content: { "application/json": { schema: { type: "object" } } } },
          "404": problemResponse("No training run yet"),
        },
      },
    },
    "/health": {
      get: {
        summary: "Data freshness",
        description: "Last successful load per dataset and the newest day of every series.",
        responses: { "200": { description: "Health", content: { "application/json": { schema: { type: "object" } } } } },
      },
    },
  },
  components: {
    schemas: {
      SeriesFrame: {
        type: "object",
        required: ["dates", "series"],
        properties: {
          dates: { type: "array", items: date },
          series: {
            type: "object",
            description: `Keys are series names: ${SERIES_NAMES.join(", ")}.`,
            additionalProperties: { type: "array", items: { type: ["number", "null"] } },
          },
        },
      },
      Forecast: {
        type: "object",
        required: ["runId", "target", "trainedAt", "points"],
        properties: {
          runId: { type: "string" },
          target: { type: "string", enum: [...FORECAST_TARGETS] },
          trainedAt: { type: "string", format: "date-time" },
          points: {
            type: "array",
            items: {
              type: "object",
              required: ["day", "horizon", "p10", "p50", "p90"],
              properties: {
                day: date,
                horizon: { type: "integer", minimum: 1 },
                p10: { type: "number" },
                p50: { type: "number" },
                p90: { type: "number" },
                drivers: {
                  type: ["array", "null"],
                  items: {
                    type: "object",
                    properties: {
                      feature: { type: "string" },
                      contribution: { type: "number" },
                      direction: { type: "string", enum: ["up", "down"] },
                    },
                  },
                },
              },
            },
          },
        },
      },
      Anomaly: {
        type: "object",
        required: ["target", "day", "severity", "direction", "method"],
        properties: {
          target: { type: "string", enum: [...FORECAST_TARGETS] },
          day: date,
          severity: { type: "number", minimum: 0 },
          direction: { type: "string", enum: ["high", "low"] },
          method: { type: "string" },
          detail: { type: ["object", "null"] },
        },
      },
      Problem: {
        type: "object",
        properties: { type: { type: "string" }, title: { type: "string" }, status: { type: "integer" }, detail: { type: "string" } },
      },
    },
  },
} as const;
