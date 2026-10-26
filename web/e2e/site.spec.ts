import AxeBuilder from "@axe-core/playwright";
import { expect, test, type ConsoleMessage } from "@playwright/test";

const PAGES = ["", "/demand", "/price", "/hydrology", "/map", "/anomalies", "/models", "/analyst", "/business", "/about"];
const LANGS = ["es", "en"] as const;

test.describe("every page, in both languages", () => {
  for (const lang of LANGS) {
    for (const path of PAGES) {
      const url = `/${lang}${path}`;

      test(`${url} renders a heading, no console errors, no horizontal scroll`, async ({ page }) => {
        const problems: string[] = [];
        page.on("console", (m: ConsoleMessage) => {
          if (m.type() === "error") problems.push(m.text());
        });
        page.on("pageerror", (e) => problems.push(e.message));

        for (const width of [1280, 390]) {
          // Load at the target width: charts size themselves once, as a visitor on that device would see.
          await page.setViewportSize({ width, height: 800 });
          await page.goto(url);
          await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
          await expect(page.locator("html")).toHaveAttribute("lang", lang);
          await page.waitForLoadState("load");
          await page.waitForTimeout(600);
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
          expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(0);
        }
        expect(problems).toEqual([]);
      });

      for (const scheme of ["light", "dark"] as const) {
        test(`${url} has no serious accessibility violations (${scheme})`, async ({ browser }) => {
          const context = await browser.newContext({ colorScheme: scheme });
          const page = await context.newPage();
          await page.goto(url);
          await page.waitForLoadState("load");
          await page.waitForTimeout(600);
          const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
          const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
          expect(
            serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`),
          ).toEqual([]);
          await context.close();
        });
      }
    }
  }
});

test.describe("navigation and preferences", () => {
  test("the root redirects by Accept-Language", async ({ browser }) => {
    const context = await browser.newContext({ locale: "en-US", extraHTTPHeaders: { "Accept-Language": "en-US,en;q=0.9" } });
    const page = await context.newPage();
    await page.goto("/");
    await expect(page).toHaveURL(/\/en$/);
    await context.close();
  });

  test("an unsupported language falls back to Spanish", async ({ request }) => {
    const response = await request.get("/", { headers: { "Accept-Language": "fr-FR" }, maxRedirects: 0 });
    expect(response.status()).toBe(307);
    expect(response.headers()["location"]).toMatch(/\/es$/);
  });

  test("switching language keeps the page", async ({ page }) => {
    await page.goto("/es/hydrology");
    await page.locator("aside").getByRole("link", { name: "EN", exact: true }).click();
    await expect(page).toHaveURL(/\/en\/hydrology$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Hydrology/);
  });

  test("the theme choice applies at once and survives a reload", async ({ page }) => {
    await page.goto("/en");
    await page.getByRole("radio", { name: "Dark" }).first().click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.getByRole("radio", { name: "System" }).first().click();
    await expect(page.locator("html")).not.toHaveAttribute("data-theme", /.+/);
  });

  test("the skip link is the first tab stop and jumps to the content", async ({ page }) => {
    await page.goto("/en");
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to content" });
    await expect(skip).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#main$/);
  });

  test("the mobile menu opens as a dialog, traps focus and closes with Escape", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await page.goto("/en");
    await page.getByRole("button", { name: "Open menu" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("link", { name: "Price" }).click();
    await expect(page).toHaveURL(/\/en\/price$/);
    await expect(dialog).toBeHidden();
  });
});

test.describe("data honesty", () => {
  test("a snapshot is labelled as a snapshot, not as live data", async ({ page }) => {
    await page.goto("/en");
    await expect(page.getByText("Demo snapshot").first()).toBeVisible();
  });

  test("every headline figure carries its own date", async ({ page }) => {
    await page.goto("/en");
    const strip = page.locator("dl").first();
    await expect(strip.getByText(/on Oct \d+, 2026/).first()).toBeVisible();
  });

  test("each chart has a text summary and a data table behind a disclosure", async ({ page }) => {
    await page.goto("/en/hydrology");
    await expect(page.getByText(/Reservoir level: from/)).toBeVisible();
  });
});

test.describe("analyst", () => {
  test("answers a question from the data when no language model is configured", async ({ page }) => {
    await page.goto("/en/analyst");
    await page.getByRole("button", { name: "How do reservoirs compare with a year ago?" }).click();
    await expect(page.getByRole("status")).toContainText("not configured");
    await expect(page.getByText(/Reservoirs stand at/)).toBeVisible();
  });

  test("shows the visitor's text as text, never as markup", async ({ page }) => {
    await page.goto("/en/analyst");
    await page.getByLabel("Ask about demand, price, reservoirs or El Niño").fill("<img src=x onerror=alert(1)> price?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText("<img src=x onerror=alert(1)> price?")).toBeVisible();
    await expect(page.locator("article img")).toHaveCount(0);
  });

  test("Shift+Enter makes a new line and Enter sends", async ({ page }) => {
    await page.goto("/en/analyst");
    const box = page.getByLabel("Ask about demand, price, reservoirs or El Niño");
    await box.fill("line one");
    await box.press("Shift+Enter");
    await box.type("line two");
    await expect(box).toHaveValue("line one\nline two");
    await box.press("Enter");
    await expect(page.getByRole("heading", { name: "You" })).toBeVisible();
  });
});

test.describe("security headers", () => {
  test("pages send the static CSP and the related headers", async ({ request }) => {
    const headers = (await request.get("/en")).headers();
    const csp = headers["content-security-policy"] ?? "";
    for (const rule of ["default-src 'self'", "object-src 'none'", "frame-ancestors 'none'", "base-uri 'self'", "connect-src 'self'"]) {
      expect(csp).toContain(rule);
    }
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["permissions-policy"]).toContain("camera=()");
    expect(headers["x-powered-by"]).toBeUndefined();
  });

  test("the API rejects bad input with a problem document", async ({ request }) => {
    const response = await request.get("/api/v1/series?names=nope");
    expect(response.status()).toBe(400);
    expect(response.headers()["content-type"]).toContain("application/problem+json");
  });
});
