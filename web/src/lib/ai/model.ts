import { google } from "@ai-sdk/google";
import type { LanguageModel } from "ai";

/**
 * The language model, or null when no key is configured (the analyst then answers from fixed
 * summaries). GEMINI_MODEL defaults to an alias that Google keeps pointing at a current Flash model,
 * so a retired model ID cannot take the analyst down. Tests replace this module.
 */
export function getChatModel(): LanguageModel | null {
  if (!process.env.GOOGLE_GENERATIVE_AI_API_KEY) return null;
  return google(process.env.GEMINI_MODEL || "gemini-flash-latest");
}
