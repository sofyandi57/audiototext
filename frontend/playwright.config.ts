import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const PORT = Number(process.env.E2E_PORT || 8765);
const root = path.resolve(__dirname, "..");
const dataDir = path.join(root, "frontend", ".e2e", "data");
const python = process.env.PYTHON || path.join(root, ".venv", "bin", "python");

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH || undefined,
      args: ["--autoplay-policy=no-user-gesture-required"],
    },
  },
  projects: [
    { name: "android-pixel7", use: { ...devices["Pixel 7"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testMatch: /layout\.spec\.ts/ },
  ],
  webServer: {
    command: `rm -rf "${dataDir}" && ${python} -m uvicorn app.main:app --host 127.0.0.1 --port ${PORT}`,
    cwd: path.join(root, "backend"),
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      MI_DATA_DIR: dataDir,
      MI_FRONTEND_DIR: path.join(root, "frontend", "out"),
      MI_WORKER_POLL_SECONDS: "0.3",
    },
  },
});
