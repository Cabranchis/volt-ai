"use client";

import { Bot, CornerDownLeft, Search, Square, UserRound } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { fmt } from "@/lib/i18n/fmt";

const MAX_CHARS = 800;
const HISTORY_LIMIT = 10;

interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  tools: string[];
}

type ErrorKind = "generic" | "rateLimited" | "tooLong";

/** The server speaks newline-delimited JSON. Anything it does not recognise is ignored. */
type ServerEvent =
  | { t: "text"; d: string }
  | { t: "tool"; name: string }
  | { t: "notice"; code: string }
  | { t: "error"; code: string }
  | { t: "done" };

function parseLine(line: string): ServerEvent | null {
  try {
    const value: unknown = JSON.parse(line);
    if (typeof value === "object" && value !== null && "t" in value) return value as ServerEvent;
  } catch {
    // A partial or corrupt line is dropped rather than shown.
  }
  return null;
}

interface Props {
  locale: Locale;
  dict: Dictionary["analyst"];
}

export function ChatPanel({ locale, dict }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<ErrorKind | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);
  const inputId = useId();

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const patchLast = (update: (m: Message) => Message) =>
    setMessages((all) => all.map((m, i) => (i === all.length - 1 ? update(m) : m)));

  async function send(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    if (text.length > MAX_CHARS) {
      setError("tooLong");
      return;
    }

    const history = [...messages, { id: nextId.current++, role: "user" as const, content: text, tools: [] }];
    setMessages([...history, { id: nextId.current++, role: "assistant", content: "", tools: [] }]);
    setInput("");
    setError(null);
    setBusy(true);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          lang: locale,
          messages: history.slice(-HISTORY_LIMIT).map(({ role, content }) => ({ role, content })),
        }),
      });
      if (!response.ok || !response.body) {
        setError(response.status === 429 ? "rateLimited" : "generic");
        setMessages((all) => all.slice(0, -1));
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          const event = parseLine(line);
          if (!event) continue;
          if (event.t === "text") patchLast((m) => ({ ...m, content: m.content + event.d }));
          else if (event.t === "tool") patchLast((m) => ({ ...m, tools: [...new Set([...m.tools, event.name])] }));
          else if (event.t === "notice" && event.code === "offline") setOffline(true);
          else if (event.t === "error") setError("generic");
        }
      }
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) setError("generic");
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(input);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(input);
    }
  }

  const errorText =
    error === "rateLimited" ? dict.rateLimited : error === "tooLong" ? fmt(dict.tooLong, { max: MAX_CHARS }) : error ? dict.error : null;

  return (
    <div className="flex flex-col gap-4">
      {offline ? (
        <p role="status" className="rounded-lg border border-line bg-surface-2 px-4 py-3 text-sm text-muted">
          {dict.offlineNotice}
        </p>
      ) : null}

      <div
        aria-live="polite"
        aria-busy={busy}
        className="glass-strong flex flex-col gap-5 rounded-panel p-5 sm:p-6"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col gap-6">
            <section aria-labelledby={`${inputId}-try`} className="flex flex-col gap-3">
              <h2 id={`${inputId}-try`} className="text-sm font-medium">
                {dict.suggestionsTitle}
              </h2>
              <ul className="flex flex-col gap-2">
                {dict.suggestions.map((suggestion) => (
                  <li key={suggestion}>
                    <button
                      type="button"
                      onClick={() => void send(suggestion)}
                      className="btn-glass flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-4 py-2.5 text-left text-sm"
                    >
                      {suggestion}
                      <CornerDownLeft aria-hidden="true" size={14} className="shrink-0 text-faint" />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
            <section aria-labelledby={`${inputId}-scope`} className="flex flex-col gap-2 border-t border-line pt-5">
              <h2 id={`${inputId}-scope`} className="text-sm font-medium">
                {dict.scopeTitle}
              </h2>
              <ul className="flex flex-wrap gap-1.5">
                {Object.values(dict.tools).map((tool) => (
                  <li
                    key={tool}
                    className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-xs text-muted"
                  >
                    <Search aria-hidden="true" size={11} />
                    {tool}
                  </li>
                ))}
              </ul>
              <p className="max-w-[60ch] text-xs leading-relaxed text-muted">{dict.scopeBody}</p>
            </section>
          </div>
        ) : (
          messages.map((message) => (
            <article key={message.id} className="flex gap-3">
              <span
                aria-hidden="true"
                className={[
                  "mt-0.5 grid size-7 shrink-0 place-items-center rounded-full",
                  message.role === "user" ? "bg-surface-2 text-muted" : "bg-accent text-on-accent",
                ].join(" ")}
              >
                {message.role === "user" ? <UserRound size={15} /> : <Bot size={15} />}
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="text-xs font-medium text-muted">
                  {message.role === "user" ? dict.youSaid : dict.analystSaid}
                </h3>
                {message.tools.length > 0 ? (
                  <p className="mt-1 flex flex-wrap gap-1.5">
                    {message.tools.map((tool) => (
                      <span
                        key={tool}
                        className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-xs text-muted"
                      >
                        <Search aria-hidden="true" size={11} />
                        {fmt(dict.toolUsed, { tool: dict.tools[tool] ?? tool })}
                      </span>
                    ))}
                  </p>
                ) : null}
                {/* Model output is shown as text, never as HTML. */}
                <p className="mt-1 whitespace-pre-wrap text-pretty leading-relaxed">
                  {message.content || (busy && message.role === "assistant" ? `${dict.sending}…` : "")}
                </p>
              </div>
            </article>
          ))
        )}
        <div ref={endRef} />
      </div>

      {errorText ? (
        <p role="alert" className="text-sm text-critical">
          {errorText}
        </p>
      ) : null}

      <form onSubmit={onSubmit} className="flex flex-col gap-2">
        <label htmlFor={inputId} className="sr-only">
          {dict.placeholder}
        </label>
        <div className="glass-strong flex items-end gap-2 rounded-panel p-2 focus-within:ring-2 focus-within:ring-focus">
          <textarea
            id={inputId}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onKeyDown}
            maxLength={MAX_CHARS + 50}
            rows={2}
            placeholder={dict.placeholder}
            className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-2 py-1.5 text-base outline-none placeholder:text-faint"
          />
          {busy ? (
            <button
              type="button"
              onClick={() => abortRef.current?.abort()}
              className="btn-glass inline-flex h-10 items-center gap-2 rounded-lg px-3.5 text-sm font-medium"
            >
              <Square aria-hidden="true" size={14} />
              {dict.stop}
            </button>
          ) : (
            <button
              type="submit"
              disabled={input.trim().length === 0}
              className="btn-primary inline-flex h-10 items-center gap-2 rounded-lg px-4 text-sm font-semibold disabled:cursor-not-allowed disabled:bg-none disabled:bg-surface-2 disabled:text-muted disabled:shadow-none"
            >
              {dict.send}
              <CornerDownLeft aria-hidden="true" size={14} />
            </button>
          )}
        </div>
        <p className="flex justify-between gap-4 text-xs text-faint">
          <span>{dict.disclaimer}</span>
          {messages.length > 0 ? (
            <button
              type="button"
              onClick={() => {
                abortRef.current?.abort();
                setMessages([]);
                setError(null);
              }}
              className="shrink-0 underline underline-offset-4 hover:text-ink"
            >
              {dict.newChat}
            </button>
          ) : null}
        </p>
      </form>
    </div>
  );
}
