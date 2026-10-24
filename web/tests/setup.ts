import { vi } from "vitest";

// "use cache" is a Next.js build-time directive and cacheLife only works inside its runtime.
// Outside Next the cached accessors are plain async functions, which is what the tests need.
vi.mock("next/cache", () => ({ cacheLife: () => undefined, cacheTag: () => undefined }));

// Tests never read a real database or call a real model.
process.env.VOLTIA_DATA_SOURCE = "fixtures";
delete process.env.DATABASE_URL_READONLY;
delete process.env.GOOGLE_GENERATIVE_AI_API_KEY;
