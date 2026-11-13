// Opt-in: runs the real UI against the real API and Gemini (costs quota). Needs the seeded demo orders
// (`python -m shopagent.cli seed`): SL-DEMO02 is paid and confirmed, so it can be cancelled by the customer.
//   npx playwright test --config playwright.live.config.ts
import { expect, test } from '@playwright/test';

test('customer: ask, get a proposal card, then decline it through the real API', async ({ page }) => {
  await page.goto('/');
  await page.locator('button.login').click();
  await page.locator('#login-email').fill('customer1@example.com');
  await page.locator('#login-password').fill('pass123');
  await page.getByRole('dialog').locator('button[type=submit]').click();
  await expect(page.locator('#login-email')).toHaveCount(0);

  const input = page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...');
  await expect(input).toBeVisible();
  await input.fill('Hủy đơn SL-DEMO02 giúp mình, mình đặt nhầm');
  await input.press('Enter');

  await expect(page.getByText('Xác nhận hủy đơn hàng SL-DEMO02')).toBeVisible({ timeout: 120000 });
  await expect(page.getByRole('button', { name: 'Xác nhận' })).toBeVisible();
  await page.getByRole('button', { name: 'Hủy', exact: true }).click();
  await expect(page.getByText('Đề xuất đã bị hủy.')).toBeVisible();

  await page.reload(); // reloading goes through GET /conversations/{id}
  await expect(page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...')).toBeVisible();
});
