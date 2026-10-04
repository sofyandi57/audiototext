import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

const ROOT = path.resolve(__dirname, "..", "..");
const FIX = path.join(ROOT, "frontend", "test-results", "fixtures");
const DATA = path.join(ROOT, "frontend", "test-results", "e2e-data");
const PY = process.env.PYTHON || path.join(ROOT, ".venv", "bin", "python");

test("meeting upload shows explicit ASR state; transcript editing and timestamps work (mobile)", async ({ page }) => {
  await page.goto("/meetings/");
  await page.getByTestId("meeting-upload").locator("input[type=file]").setInputFiles(path.join(FIX, "rapat.wav"));
  await page.getByLabel("Judul (opsional)").fill("Rapat Uji");
  await page.getByRole("button", { name: "Unggah & proses" }).click();
  await expect(page).toHaveURL(/\/meetings\/view\/\?id=mtg_/);
  const id = new URL(page.url()).searchParams.get("id")!;

  // Without a downloadable ASR model this server must say so (not pretend).
  const failed = page.getByTestId("meeting-failed");
  const ready = page.getByText("Siap", { exact: true });
  await expect(failed.or(ready)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("player").locator("audio")).toBeVisible(); // playback works regardless

  if (await failed.isVisible()) {
    await expect(failed).toContainText("Transkripsi belum bisa dijalankan");
    await expect(page.getByRole("button", { name: "Ulangi" })).toBeVisible();
    // seed a transcript to exercise the review UI, then analyse
    execFileSync(PY, [path.join(__dirname, "seed_transcript.py"), DATA, id]);
    await page.request.post(`/api/meetings/${id}/analyze`);
    await page.reload();
  }

  await page.getByRole("tab", { name: "Transkrip" }).click();
  const segs = page.getByTestId("segment");
  await expect(segs).toHaveCount(4, { timeout: 20_000 });

  // speaker label correction
  await segs.nth(1).getByTestId("speaker-label").click();
  await segs.nth(1).getByLabel("Nama pembicara").fill("Budi");
  await segs.nth(1).getByRole("button", { name: "Simpan" }).click();
  await expect(segs.nth(1).getByTestId("speaker-label")).toHaveText("Budi");

  // text correction keeps original ASR output visible
  await segs.nth(0).getByRole("button", { name: "edit" }).click();
  await segs.nth(0).getByLabel("Teks segmen").fill("Selamat pagi semua, kita mulai rapat evaluasi.");
  await segs.nth(0).getByRole("button", { name: "Simpan" }).click();
  await expect(segs.nth(0)).toContainText("diedit");

  // timestamp seeks the player
  await segs.nth(2).getByRole("button", { name: /Putar dari/ }).click();
  await page.waitForFunction(() => {
    const a = document.querySelector("[data-testid=player] audio") as HTMLAudioElement | null;
    return !!a && a.currentTime >= 3.0;
  }, null, { timeout: 10_000 });

  // re-analyse and check provenance in the UI
  await page.getByRole("button", { name: "Analisis ulang" }).click();
  await page.getByRole("tab", { name: /Tindak lanjut/ }).click();
  const actions = page.getByTestId("insights");
  await expect(actions).toContainText("Tolong Budi siapkan dokumentasi API", { timeout: 20_000 });
  await expect(actions).toContainText("paling lambat hari Jumat");
  await actions.getByRole("button", { name: /lihat di transkrip/ }).first().click();
  await expect(page.getByRole("tab", { name: "Transkrip" })).toHaveAttribute("aria-selected", "true");

  await page.getByRole("tab", { name: "Pembicara" }).click();
  await expect(page.getByTestId("speakers")).toContainText("Budi");

  const md = await page.request.get(`/api/meetings/${id}/export.md`);
  expect(await md.text()).toContain("**Budi:**");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
