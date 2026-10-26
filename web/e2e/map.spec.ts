import { expect, test } from "@playwright/test";

test("map keeps its zoom while another reservoir is picked", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/es/map");
  await page.waitForTimeout(1000);
  const svg = page.locator("svg[role=group]");
  const box = async () => (await svg.getAttribute("viewBox")) ?? "";
  const full = await box();

  await page.getByText("Antioquia", { exact: true }).first().click();
  await page.waitForTimeout(1300);
  const antioquia = await box();
  expect(antioquia).not.toBe(full);

  // another reservoir of the same region: same view, row highlighted
  await page.locator("g[role=button]", { hasText: "Ituango" }).first().locator("circle").last().click();
  await page.waitForTimeout(1300);
  expect(await box()).toBe(antioquia);
  await expect(page.locator("tr[aria-current=true]")).toContainText("Ituango");

  // clicking the chosen one again steps back out to the whole country
  await page.locator("tr[aria-current=true] button").click();
  await page.waitForTimeout(1300);
  expect(await box()).toBe(full);
  await expect(page.locator("tr[aria-current=true]")).toHaveCount(0);

  // clicking the empty map while zoomed in does the same
  await page.getByText("Antioquia", { exact: true }).first().click();
  await page.waitForTimeout(1300);
  expect(await box()).not.toBe(full);
  await svg.click({ position: { x: 20, y: 20 } });
  await page.waitForTimeout(1300);
  expect(await box()).toBe(full);

  // a reservoir of another region moves there directly
  await page.locator("table button", { hasText: "Betania" }).click();
  await page.waitForTimeout(1300);
  expect(await box()).not.toBe(full);
  await expect(page.locator("tr[aria-current=true]")).toContainText("Betania");
});
