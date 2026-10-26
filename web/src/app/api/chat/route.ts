import { isStepCount, streamText, type LanguageModel, type ModelMessage } from "ai";
import { z } from "zod";
import { problem } from "@/lib/api";
import { answerOffline } from "@/lib/ai/offline";
import { getChatModels } from "@/lib/ai/model";
import {
  MAX_MESSAGE_CHARS,
  MAX_MESSAGES,
  MAX_STEPS,
  MAX_TOTAL_CHARS,
  systemPrompt,
} from "@/lib/ai/prompt";
import { clientKeyFor, getRateLimiter } from "@/lib/ai/ratelimit";
import { buildTools } from "@/lib/ai/tools";
import type { Locale } from "@/lib/i18n/config";

export const maxDuration = 30;

const MAX_BODY_BYTES = 16_384;
const PER_CLIENT_LIMIT = 12;
const PER_CLIENT_WINDOW_SEC = 600;
const DAILY_LIMIT = Number(process.env.CHAT_DAILY_LIMIT ?? 400);

const bodySchema = z
  .object({
    lang: z.enum(["es", "en"]),
    messages: z
      .array(
        z.object({
          role: z.enum(["user", "assistant"]),
          content: z.string().trim().min(1).max(MAX_MESSAGE_CHARS),
        }),
      )
      .min(1)
      .max(MAX_MESSAGES),
  })
  .refine((body) => body.messages.at(-1)?.role === "user", { message: "The last message must come from the user." })
  .refine((body) => body.messages.reduce((n, m) => n + m.content.length, 0) <= MAX_TOTAL_CHARS, {
    message: "The conversation is too long.",
  });

type ChatEvent =
  | { t: "text"; d: string }
  | { t: "tool"; name: string }
  | { t: "notice"; code: "offline" }
  | { t: "error"; code: "model"; reason?: string }
  | { t: "done" };

const bogotaToday = (): string =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota" }).format(new Date());

/** Newline-delimited JSON, one event per line: simple to read in the browser and independent of SDK versions. */
function eventStream(produce: (send: (event: ChatEvent) => void) => Promise<void>): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (event: ChatEvent) => controller.enqueue(encoder.encode(`${JSON.stringify(event)}\n`));
      try {
        await produce(send);
        send({ t: "done" });
      } catch (error) {
        send({ t: "error", code: "model", reason: error instanceof ModelFailure ? error.reason : undefined });
      } finally {
        controller.close();
      }
    },
  });
  return new Response(stream, {
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true; // Non-browser clients; they are rate limited like everyone else.
  try {
    return new URL(origin).host === request.headers.get("host");
  } catch {
    return false;
  }
}

/** A failure whose reason is safe to send to the browser: a finish reason or an HTTP status, never provider text. */
class ModelFailure extends Error {
  constructor(readonly reason: string) {
    super(reason);
  }
}

function statusOf(error: unknown): string {
  const status = (error as { statusCode?: unknown } | null)?.statusCode;
  if (typeof status === "number") return `provider status ${status}`;
  const name = (error as { name?: unknown } | null)?.name;
  return typeof name === "string" && /^[A-Za-z_]{1,48}$/.test(name) ? `provider error ${name}` : "provider error";
}

export async function POST(request: Request) {
  if (!sameOrigin(request)) return problem(403, "Cross-origin requests are not allowed");

  const declared = Number(request.headers.get("content-length") ?? 0);
  if (declared > MAX_BODY_BYTES) return problem(413, "Request too large");
  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) return problem(413, "Request too large");

  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return problem(400, "Body must be JSON");
  }
  const parsed = bodySchema.safeParse(json);
  if (!parsed.success) {
    return problem(400, "Invalid request", parsed.error.issues.map((i) => i.message).join("; "));
  }
  const { lang, messages } = parsed.data;
  const locale: Locale = lang;

  const key = await clientKeyFor(request.headers);
  const limiter = await getRateLimiter();

  const mine = await limiter.hit(`chat:${key}`, PER_CLIENT_LIMIT, PER_CLIENT_WINDOW_SEC);
  if (!mine.allowed) {
    const response = problem(429, "Too many requests", "Wait a few minutes and try again.");
    response.headers.set("Retry-After", String(mine.retryAfterSec));
    return response;
  }
  const global = await limiter.hit("chat:global", DAILY_LIMIT, 86_400);

  const models = getChatModels();
  const question = messages.at(-1)?.content ?? "";

  // No key, or the day's quota for the language model is spent: answer from fixed summaries.
  if (models.length === 0 || !global.allowed) {
    return eventStream(async (send) => {
      send({ t: "notice", code: "offline" });
      send({ t: "text", d: await answerOffline(question, locale) });
    });
  }

  const modelMessages: ModelMessage[] = messages.map((m) => ({ role: m.role, content: m.content }));
  return eventStream(async (send) => {
    // Try each model in turn. A failure after text has gone out cannot be retried: the browser has it.
    let failure: ModelFailure | undefined;
    for (const [index, model] of models.entries()) {
      const last = index === models.length - 1;
      let sentText = false;
      try {
        await streamAnswer(model, last ? 12_000 : 14_000, () => {
          sentText = true;
        });
        return;
      } catch (error) {
        failure = error instanceof ModelFailure ? error : new ModelFailure("provider error");
        if (sentText) throw failure;
      }
    }
    throw failure ?? new ModelFailure("no model");

    async function streamAnswer(model: LanguageModel, totalMs: number, onText: () => void) {
      const result = streamText({
        model,
        instructions: systemPrompt(locale, bogotaToday()),
        messages: modelMessages,
        tools: buildTools(locale),
        stopWhen: isStepCount(MAX_STEPS),
        maxOutputTokens: 700,
        temperature: 0.2,
        maxRetries: 0,
        // No abortSignal from the request: on Vercel it fires at once and ends the stream empty.
        // The timeouts bound the cost of an abandoned request; together they fit maxDuration.
        timeout: { totalMs },
      });
      let answered = false;
      let finish = "no finish event";
      for await (const part of result.fullStream) {
        if (part.type === "text-delta") {
          if (part.text) {
            answered = true;
            onText();
          }
          send({ t: "text", d: part.text });
        } else if (part.type === "tool-call") send({ t: "tool", name: part.toolName });
        else if (part.type === "error") throw new ModelFailure(statusOf(part.error));
        else if (part.type === "abort") finish = "aborted";
        else if (part.type === "finish") finish = String(part.finishReason);
      }
      // A stream that ends without any text is a failure, not an empty answer.
      if (!answered) throw new ModelFailure(`empty answer, finish: ${finish}`);
    }
  });
}
