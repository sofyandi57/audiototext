import { expect, test } from "@playwright/test";

test("manifest is installable-shaped and icons resolve", async ({ page, request }) => {
  await page.goto("/");
  const href = await page.locator('link[rel="manifest"]').getAttribute("href");
  expect(href).toBe("/manifest.webmanifest");
  const res = await request.get(href!);
  expect(res.headers()["content-type"]).toContain("manifest+json");
  const m = await res.json();
  expect(m.display).toBe("standalone");
  expect(m.start_url).toBe("/");
  const sizes = m.icons.map((i: any) => `${i.sizes}:${i.purpose}`);
  expect(sizes).toEqual(expect.arrayContaining(["192x192:any", "512x512:any", "512x512:maskable"]));
  for (const icon of m.icons) {
    const r = await request.get(icon.src);
    expect(r.status()).toBe(200);
    expect(r.headers()["content-type"]).toBe("image/png");
  }
  expect(await page.locator('meta[name="theme-color"]').getAttribute("content")).toBe("#1f5fbf");
});

test("service worker caches the shell but never /api (privacy)", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  // make sure the SW controls the page, then hit private API routes through it
  await page.reload();
  await page.waitForFunction(() => !!navigator.serviceWorker.controller);
  await page.evaluate(async () => {
    await fetch("/api/documents");
    await fetch("/api/capabilities");
  });
  const cached: string[] = await page.evaluate(async () => {
    const out: string[] = [];
    for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(new URL(r.url).pathname);
    return out;
  });
  expect(cached).toContain("/offline.html");
  expect(cached.some((p) => p.startsWith("/api/"))).toBe(false);
});

test("offline page is shown when the server is unreachable", async ({ page, context }) => {
  await page.goto("/settings/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await page.waitForFunction(() => !!navigator.serviceWorker.controller);
  await context.setOffline(true);
  await page.goto("/meetings/").catch(() => undefined);
  await expect(page.locator("h1")).toBeVisible();
  await context.setOffline(false);
});
