// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorScreen } from "./ErrorScreen";
import { ERROR_TEXT, errorLocale } from "@/lib/i18n/errors";

afterEach(cleanup);

describe("ErrorScreen", () => {
  it("says the data is unavailable instead of showing numbers, and offers a retry", () => {
    const retry = vi.fn();
    render(<ErrorScreen locale="en" retry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent(ERROR_TEXT.en.title);
    expect(screen.getByRole("alert")).toHaveTextContent("Nothing is shown in its place");
    fireEvent.click(screen.getByRole("button", { name: ERROR_TEXT.en.retry }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("speaks Spanish for anything that is not English", () => {
    expect(errorLocale("es")).toBe("es");
    expect(errorLocale("en")).toBe("en");
    expect(errorLocale(undefined)).toBe("es");
    render(<ErrorScreen locale={errorLocale("fr")} retry={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Datos no disponibles");
  });
});
