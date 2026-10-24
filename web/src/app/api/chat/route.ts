import { isStepCount, streamText, type ModelMessage } from "ai";
import { z } from "zod";
import { problem } from "@/lib/api";
import { answerOffline } from "@/lib/ai/offline";
import { getChatModel } from "@/lib/ai/model";
import {
  MAX_MESSAGE_CHARS,
  MAX_MESSAGES,
  MAX_STEPS,
  MAX_TOTAL_CHARS,
  systemPrompt,
} from "@/lib/ai/prompt";
import { clientKey, getRateLimiter } from "@/lib/ai/ratelimit";
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
  | { t: "error"; code: "model" }
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
      } catch {
        send({ t: "error", code: "model" });
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

  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const address = forwarded || request.headers.get("x-real-ip") || "unknown";
  const key = await clientKey(address, process.env.RATE_LIMIT_SALT ?? "voltia");
  const limiter = await getRateLimiter();

  const mine = await limiter.hit(`chat:${key}`, PER_CLIENT_LIMIT, PER_CLIENT_WINDOW_SEC);
  if (!mine.allowed) {
    const response = problem(429, "Too many requests", "Wait a few minutes and try again.");
    response.headers.set("Retry-After", String(mine.retryAfterSec));
    return response;
  }
  const global = await limiter.hit("chat:global", DAILY_LIMIT, 86_400);

  const model = getChatModel();
  const question = messages.at(-1)?.content ?? "";

  // No key, or the day's quota for the language model is spent: answer from fixed summaries.
  if (!model || !global.allowed) {
    return eventStream(async (send) => {
      send({ t: "notice", code: "offline" });
      send({ t: "text", d: await answerOffline(question, locale) });
    });
  }

  const modelMessages: ModelMessage[] = messages.map((m) => ({ role: m.role, content: m.content }));
  return eventStream(async (send) => {
    const result = streamText({
      model,
      instructions: systemPrompt(locale, bogotaToday()),
      messages: modelMessages,
      tools: buildTools(locale),
      stopWhen: isStepCount(MAX_STEPS),
      maxOutputTokens: 700,
      temperature: 0.2,
      abortSignal: request.signal,
      timeout: { totalMs: 25_000 },
    });
    for await (const part of result.fullStream) {
      if (part.type === "text-delta") send({ t: "text", d: part.text });
      else if (part.type === "tool-call") send({ t: "tool", name: part.toolName });
      else if (part.type === "error") throw new Error("model stream error");
    }
  });
}
