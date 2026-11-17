import { defineConfig } from "@playwright/test";

// Usa o Edge do sistema (PLAYWRIGHT_CHANNEL=msedge) ou o Chromium do Playwright no CI.
export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  use: { baseURL: "http://localhost:5102", channel: process.env.PLAYWRIGHT_CHANNEL || undefined },
  webServer: [
    { command: "uv run --directory ../backend uvicorn app.main:app --port 8102", url: "http://127.0.0.1:8102/api/health", reuseExistingServer: true },
    { command: "pnpm exec vite --port 5102 --strictPort", url: "http://localhost:5102", reuseExistingServer: true },
  ],
});
