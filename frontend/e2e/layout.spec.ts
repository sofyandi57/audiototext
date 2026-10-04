import { expect, test } from "@playwright/test";

const PAGES = ["/", "/meetings/", "/audiobooks/", "/jobs/", "/settings/"];

for (const url of PAGES) {
  test(`no horizontal overflow and navigation reachable: ${url}`, async ({ page }) => {
    await page.goto(url);
    await expect(page.locator("h1")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    const links = page.getByRole("navigation", { name: "Navigasi utama" }).locator("ul a");
    await expect(links).toHaveCount(5);
    for (const box of await links.evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height))) {
      expect(box).toBeGreaterThanOrEqual(44); // touch target
    }
  });
}

test("navigation between modules works", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Navigasi utama" }).getByRole("link", { name: /Audiobook/ }).click();
  await expect(page).toHaveURL(/\/audiobooks\/$/);
  await expect(page.getByRole("heading", { name: "PDF Audiobook" })).toBeVisible();
  await page.getByRole("navigation", { name: "Navigasi utama" }).getByRole("link", { name: /Settings/ }).click();
  await expect(page.getByTestId("capabilities")).toBeVisible();
});

test("empty states are shown", async ({ page }) => {
  await page.goto("/jobs/");
  await expect(page.locator(".empty, [data-testid=jobs]")).toBeVisible();
});
