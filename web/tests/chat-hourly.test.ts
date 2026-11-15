import { MockLanguageModelV4 } from "ai/test";
import { simulateReadableStream } from "ai";
import { describe, expect, it, vi } from "vitest";

const holder = vi.hoisted(() => {
  process.env.CHAT_HOURLY_LIMIT = "3"; // read per request, so a small cap can be tested
  return { model: null as unknown };
});
vi.mock("@/lib/ai/model", () => ({ getChatModels: () => (holder.model ? [holder.model] : []) }));

import { POST } from "@/app/api/chat/route";

const usage = {
  inputTokens: { total: 1, noCache: 1, cacheRead: undefined, cacheWrite: undefined },
  outputTokens: { total: 1, text: 1, reasoning: undefined },
};

describe("the hourly cap on the language model", () => {
  it("sends the questions over the cap to the fixed summaries, which cost nothing", async () => {
    const model = new MockLanguageModelV4({
      doStream: async () => ({
        stream: simulateReadableStream({
          chunks: [
            { type: "text-start", id: "t" },
            { type: "text-delta", id: "t", delta: "From the model." },
            { type: "text-end", id: "t" },
            { type: "finish", finishReason: { unified: "stop", raw: undefined }, logprobs: undefined, usage },
          ] as never,
        }),
      }),
    });
    holder.model = model;
    const ask = (i: number) =>
      POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json", host: "localhost", "x-forwarded-for": `198.51.100.${i}` },
          body: JSON.stringify({ lang: "en", messages: [{ role: "user", content: "How is demand?" }] }),
        }),
      );
    const texts: string[] = [];
    for (let i = 1; i <= 5; i++) texts.push(await (await ask(i)).text());
    expect(texts.slice(0, 3).every((t) => t.includes("From the model."))).toBe(true);
    expect(texts.slice(3).every((t) => t.includes('"code":"offline"'))).toBe(true);
    expect(model.doStreamCalls).toHaveLength(3);
  });
});
