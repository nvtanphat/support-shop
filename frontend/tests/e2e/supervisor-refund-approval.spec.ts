import { expect, test } from '@playwright/test';
import { json, mockConversation, signInAsStaff } from './helpers';

test('a refund over the limit waits for a supervisor; a decision is blocked until a note is written', async ({ page }) => {
  await signInAsStaff(page, 'supervisor');
  let decision: { decision?: string; note?: string } | null = null;
  await mockConversation(page, 'conv-sup');
  await page.route('**/api/staff/approvals?*', (route) =>
    json(route, {
      approvals: [
        { id: 'apr-b', gate: 'B_refund', subject_type: 'refund', subject_id: 'bbbbbbbb-0000-0000-0000-000000000002', status: 'pending', required_role: 'supervisor', risk_flags: [], requested_at: new Date().toISOString() },
      ],
    })
  );
  await page.route('**/api/staff/approvals/apr-b/decision', async (route) => {
    decision = route.request().postDataJSON();
    await json(route, { status: 'rejected' });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Nhân viên' }).click();
  await expect(page.getByText('Cổng: B_refund')).toBeVisible();
  await expect(page.getByText('Vai trò yêu cầu: supervisor')).toBeVisible();
  await page.getByRole('button', { name: /Xem xét/ }).click();

  await expect(page.getByRole('button', { name: /Từ chối/ })).toBeDisabled();
  await expect(page.getByRole('button', { name: /Chấp thuận/ })).toBeDisabled();
  expect(decision).toBeNull(); // nothing can be sent without a note

  await page.getByPlaceholder('Nhập lý do duyệt hoặc lý do từ chối...').fill('Giá trị hoàn vượt hạn mức, cần chứng từ thanh toán');
  await page.getByRole('button', { name: /Từ chối/ }).click();
  await expect.poll(() => decision?.decision).toBe('reject');
});
