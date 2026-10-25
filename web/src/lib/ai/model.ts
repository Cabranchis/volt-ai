import { google } from "@ai-sdk/google";
import type { LanguageModel } from "ai";

/**
 * The language models to try, in order; empty when no key is configured (the analyst then answers from
 * fixed summaries). GEMINI_MODEL defaults to an alias that Google keeps pointing at a current Flash model,
 * so a retired model ID cannot take the analyst down. Flash is sometimes overloaded (503), so the lighter
 * Flash-Lite follows it as a fallback. Tests replace this module.
 */
export function getChatModels(): LanguageModel[] {
  if (!process.env.GOOGLE_GENERATIVE_AI_API_KEY) return [];
  const primary = process.env.GEMINI_MODEL || "gemini-flash-latest";
  const fallback = process.env.GEMINI_FALLBACK_MODEL || "gemini-flash-lite-latest";
  return [...new Set([primary, fallback])].map((id) => google(id));
}
