import { expect, test } from "@playwright/test";
import path from "node:path";

const FIX = path.resolve(__dirname, "..", "test-results", "fixtures");

test("PDF upload -> review -> edit -> generate audio -> play -> download (mobile)", async ({ page, request }) => {
  await page.goto("/audiobooks/");
  await page.getByTestId("pdf-upload").locator("input[type=file]").setInputFiles(path.join(FIX, "buku.pdf"));
  await page.getByRole("button", { name: "Unggah & proses" }).click();
  await expect(page).toHaveURL(/\/audiobooks\/view\/\?id=doc_/);
  await expect(page.getByText("Siap ditinjau")).toBeVisible({ timeout: 30_000 });

  const chapters = page.getByTestId("chapter-list").locator("li");
  await expect(chapters).toHaveCount(3);
  await expect(chapters.first()).toContainText("BAB I PENDAHULUAN");

  // correct the extracted text before generating audio
  const editor = page.getByTestId("section-text");
  await editor.fill((await editor.inputValue()) + "\n\nKalimat koreksi dari pengguna.");
  await page.getByRole("button", { name: "Simpan koreksi" }).click();
  await expect(page.getByText("Tersimpan.")).toBeVisible();
  await expect(chapters.first()).toContainText("diedit");

  // cleaning report is visible, not silent
  await page.getByRole("tab", { name: "Pembersihan" }).click();
  await expect(page.getByTestId("cleaning-report")).toContainText("Header berulang");
  await page.getByRole("tab", { name: "Pratinjau PDF" }).click();
  await expect(page.locator("img.page-preview")).toBeVisible();
  expect(await page.locator("img.page-preview").evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(100);
  await page.getByRole("tab", { name: "Bab & teks" }).click();

  await page.getByTestId("generate-all").click();
  await expect(page.getByText("Siap", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(chapters.nth(2)).toContainText("audio");

  await page.getByTestId("play-section").click();
  const audio = page.getByTestId("player").locator("audio");
  await expect(audio).toBeVisible();
  await page.waitForFunction(() => {
    const a = document.querySelector("[data-testid=player] audio") as HTMLAudioElement | null;
    return !!a && a.currentTime > 0.3;
  }, null, { timeout: 15_000 });

  // playback speed control
  await page.getByLabel("Kecepatan putar").selectOption("1.5");
  expect(await audio.evaluate((a: HTMLAudioElement) => a.playbackRate)).toBe(1.5);

  // player sits above the bottom navigation, not behind it
  const playerBox = await page.getByTestId("player").boundingBox();
  const navBox = await page.getByRole("navigation", { name: "Navigasi utama" }).boundingBox();
  expect(playerBox!.y + playerBox!.height).toBeLessThanOrEqual(navBox!.y + 1);

  // progress persisted for "continue listening"
  const saved = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("ab:")).length);
  expect(saved).toBe(1);

  const href = await page.getByTestId("download-book").getAttribute("href");
  const res = await request.get(href!);
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toBe("audio/mpeg");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("scanned PDF pages are flagged or OCR'd, never silently skipped", async ({ page }) => {
  await page.goto("/audiobooks/");
  await page.getByTestId("pdf-upload").locator("input[type=file]").setInputFiles(path.join(FIX, "pindaian.pdf"));
  await page.getByRole("button", { name: "Unggah & proses" }).click();
  await expect(page.getByText("Siap ditinjau")).toBeVisible({ timeout: 60_000 });
  await page.getByRole("tab", { name: "Pembersihan" }).click();
  const report = page.getByTestId("cleaning-report");
  const ocrUsed = (await report.textContent())!.includes("Halaman OCR1");
  if (!ocrUsed) await expect(page.getByTestId("review-pages")).toBeVisible();
  else await expect(report).toContainText("Halaman OCR1");
});

test("client-side validation rejects non-PDF", async ({ page }) => {
  await page.goto("/audiobooks/");
  await page.getByTestId("pdf-upload").locator("input[type=file]").setInputFiles({
    name: "catatan.txt", mimeType: "text/plain", buffer: Buffer.from("halo"),
  });
  await expect(page.getByTestId("pdf-upload").getByRole("alert")).toContainText("tidak didukung");
});
