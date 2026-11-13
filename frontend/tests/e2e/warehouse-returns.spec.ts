import { expect, test } from '@playwright/test';
import { json, mockConversation, signInAsStaff } from './helpers';

test('staff receive a returned parcel and record the inspection from the portal', async ({ page }) => {
  await signInAsStaff(page);
  await mockConversation(page, 'conv-wh');
  await page.route('**/api/staff/approvals?*', (route) => json(route, { approvals: [] }));
  let status = 'awaiting_return';
  const calls: string[] = [];
  await page.route('**/api/staff/returns', (route) =>
    json(route, { returns: [{ code: 'RT-WH0001', order_code: 'SL-WH0001', status, reason_code: 'defective', resolution: 'refund', evidence_count: 2, created_at: new Date().toISOString() }] })
  );
  await page.route('**/api/staff/returns/RT-WH0001/receive', (route) => {
    calls.push('receive');
    status = 'received';
    return json(route, { code: 'RT-WH0001', status });
  });
  await page.route('**/api/staff/returns/RT-WH0001/inspection', (route) => {
    calls.push('inspect');
    status = 'accepted';
    return json(route, { message: 'Kiểm hàng đạt chuẩn.', refund_code: 'RF-WH0001', refund_amount: 450000, needs_approval: false });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Nhân viên' }).click();
  await page.getByRole('button', { name: /Kho hàng trả về/ }).click();
  await expect(page.getByText('RT-WH0001')).toBeVisible();
  await page.getByRole('button', { name: 'Xác nhận đã nhận hàng' }).click();
  await page.getByRole('button', { name: 'Kiểm hàng đạt' }).click();
  await expect(page.getByText(/RF-WH0001: 450\.000 đ/)).toBeVisible();
  expect(calls).toEqual(['receive', 'inspect']);
});
