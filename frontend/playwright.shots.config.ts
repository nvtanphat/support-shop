import { defineConfig, devices } from '@playwright/test';

// Chụp ảnh giao diện cho README bằng API giả lập: npm run shots
export default defineConfig({
  testDir: './tests/shots',
  workers: 1,
  reporter: 'list',
  use: { baseURL: process.env.SHOTS_URL ?? 'http://localhost:5173', headless: true, viewport: { width: 1360, height: 820 }, deviceScaleFactor: 2 },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1360, height: 820 }, deviceScaleFactor: 2 } }],
  webServer: { command: 'npm run dev', url: process.env.SHOTS_URL ?? 'http://localhost:5173', reuseExistingServer: true, timeout: 30000 },
});
