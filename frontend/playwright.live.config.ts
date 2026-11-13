import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/live',
  timeout: 180000,
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://localhost:5173', headless: true, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
