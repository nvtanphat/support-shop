// Opt-in exploratory sweep against the real API: clicks every main control and records console
// errors and failed requests. Run: npx playwright test --config playwright.live.config.ts explore
import { expect, test, Page } from '@playwright/test';

function watch(page: Page, problems: string[]) {
  page.on('console', (m) => m.type() === 'error' && problems.push(`console: ${m.text()}`));
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('response', (r) => {
    if (r.url().includes('/api/') && r.status() >= 400) problems.push(`${r.status()} ${r.request().method()} ${r.url().replace(/.*\/api/, '/api')}`);
  });
}

test('guest: every header and hero control, policies, OTP dialog', async ({ page }) => {
  const problems: string[] = [];
  watch(page, problems);
  await page.goto('/');
  for (const name of ['Chính sách', 'Tra cứu đơn hàng', 'Đổi trả', 'Liên hệ']) {
    await page.getByRole('navigation').getByRole('button', { name }).click();
    await page.waitForTimeout(1500);
    await page.keyboard.press('Escape');
  }
  for (const name of ['Tra cứu đơn hàng', 'Đổi trả / Hoàn tiền', 'Hỏi về chính sách', 'Hỗ trợ khác']) {
    const b = page.getByRole('main').getByRole('button', { name });
    if (await b.count()) { await b.first().click(); await page.waitForTimeout(1500); await page.keyboard.press('Escape'); }
  }
  const verify = page.getByRole('button', { name: 'Xác minh đơn hàng' });
  if (await verify.count()) { await verify.first().click(); await page.waitForTimeout(800); await page.keyboard.press('Escape'); }
  const related = page.getByRole('complementary').getByRole('button').first();
  if (await related.count()) { await related.click(); await page.waitForTimeout(1000); await page.keyboard.press('Escape'); }
  console.log('GUEST PROBLEMS\n' + problems.join('\n'));
});

test('staff roles: every tab', async ({ page }) => {
  const problems: string[] = [];
  watch(page, problems);
  for (const [email, pw] of [['agent@shop.vn', 'staff123'], ['supervisor@shop.vn', 'staff123'], ['admin@shop.vn', 'admin123']]) {
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.locator('button.login').click();
    const staffToggle = page.getByRole('dialog').getByRole('button', { name: /nhân viên/i });
    if (await staffToggle.count()) await staffToggle.first().click();
    await page.locator('#login-email').fill(email);
    await page.locator('#login-password').fill(pw);
    await page.getByRole('dialog').locator('button[type=submit]').click();
    await page.waitForTimeout(1500);
    const staffTab = page.getByRole('button', { name: 'Nhân viên' });
    if (!(await staffTab.count())) { problems.push(`${email}: no staff tab after login`); continue; }
    await staffTab.click();
    for (const tab of ['Hàng chờ duyệt', 'Phiếu & Hội thoại', 'Kho hàng trả về', 'Vận hành', 'Bảng mô phỏng']) {
      const b = page.getByRole('button', { name: new RegExp(tab) });
      if (await b.count()) { await b.first().click(); await page.waitForTimeout(1200); }
    }
    await expect(page.locator('body')).toBeVisible();
  }
  console.log('STAFF PROBLEMS\n' + problems.join('\n'));
});

test('customer: order lookup, order card actions, policy links, upload dialog', async ({ page }) => {
  const problems: string[] = [];
  watch(page, problems);
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.locator('button.login').click();
  await page.locator('#login-email').fill('customer1@example.com');
  await page.locator('#login-password').fill('pass123');
  await page.getByRole('dialog').locator('button[type=submit]').click();
  await expect(page.locator('#login-email')).toHaveCount(0);
  await page.waitForTimeout(1500);

  const input = page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...');
  await input.fill('Kiểm tra đơn SL-000900 giúp mình');
  await input.press('Enter');
  await expect(page.getByText('SL-000900').first()).toBeVisible({ timeout: 120000 });
  await page.waitForTimeout(3000);
  for (const name of [/Xem chi tiết chính sách/, /Tạo yêu cầu đổi trả/]) {
    const b = page.getByRole('button', { name });
    if (await b.count()) { await b.first().click(); await page.waitForTimeout(4000); await page.keyboard.press('Escape'); }
  }
  const cite = page.locator('button', { hasText: /POL-/ }).first();
  if (await cite.count()) { await cite.click(); await page.waitForTimeout(1500); await page.keyboard.press('Escape'); }
  await page.reload();
  await page.waitForTimeout(2500);
  console.log('CUSTOMER PROBLEMS\n' + problems.join('\n'));
  await page.screenshot({ path: 'test-results/customer-after-reload.png', fullPage: true });
});
