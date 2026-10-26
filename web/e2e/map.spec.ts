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

  // clicking it again clears the highlight but keeps the zoom
  await page.locator("tr[aria-current=true] button").click();
  await page.waitForTimeout(500);
  expect(await box()).toBe(antioquia);
  await expect(page.locator("tr[aria-current=true]")).toHaveCount(0);

  // a reservoir of another region moves there directly
  await page.getByText("Todo el país").first().click();
  await page.waitForTimeout(1300);
  await page.locator("table button", { hasText: "Betania" }).click();
  await page.waitForTimeout(1300);
  expect(await box()).not.toBe(full);
  await expect(page.locator("tr[aria-current=true]")).toContainText("Betania");
});
