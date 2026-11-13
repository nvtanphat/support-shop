import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/live',
  timeout: 180000,
  workers: 1,
  reporter: 'list',
  // LIVE_BASE_URL points the run at another dev server (for example one proxied to a different API port).
  use: { baseURL: process.env.LIVE_BASE_URL ?? 'http://localhost:5173', headless: true, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
