import { expect, test } from '@playwright/test';
import { json, mockConversation, pendingAction } from './helpers';

test('customer cancels an order by pressing the confirm button, which sends the preview hash', async ({ page }) => {
  const conv = 'conv-cancel';
  let confirmBody: { preview_hash?: string; payload_hash?: string } = {};
  await mockConversation(page, conv);
  await page.route(`**/api/conversations/${conv}/messages`, (route) =>
    json(route, {
      status: 'success',
      assistant_message: 'Đơn SL-CAN001 chưa giao nên có thể hủy. Quý khách xác nhận bên dưới.',
      citations: [],
      pending_action: pendingAction(conv, {
        id: 'act-cancel-1',
        type: 'cancel_order',
        title: 'Hủy đơn hàng SL-CAN001',
        description: 'Lý do: đặt nhầm sản phẩm',
        extra: { order_code: 'SL-CAN001' },
      }),
    })
  );
  await page.route('**/api/actions/act-cancel-1/confirm', async (route) => {
    confirmBody = route.request().postDataJSON();
    await json(route, { status: 'confirmed', result: { order_status: 'cancelled' } });
  });

  await page.goto('/');
  const input = page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...');
  await input.fill('Mình muốn hủy đơn SL-CAN001');
  await input.press('Enter');

  await expect(page.getByText('Hủy đơn hàng SL-CAN001')).toBeVisible();
  await page.getByRole('button', { name: 'Xác nhận' }).click();
  await expect(page.getByText('Đã xác nhận thành công!')).toBeVisible();
  expect(Object.values(confirmBody)).toContain('hash-act-cancel-1');
});

test('declining a cancellation proposal cancels the action instead of confirming it', async ({ page }) => {
  const conv = 'conv-cancel-decline';
  let confirmCalls = 0;
  await mockConversation(page, conv);
  await page.route(`**/api/conversations/${conv}/messages`, (route) =>
    json(route, {
      status: 'success',
      assistant_message: 'Quý khách xác nhận hủy đơn SL-CAN002?',
      citations: [],
      pending_action: pendingAction(conv, { id: 'act-cancel-2', type: 'cancel_order', title: 'Hủy đơn hàng SL-CAN002', description: 'Đặt nhầm' }),
    })
  );
  await page.route('**/api/actions/act-cancel-2/confirm', (route) => {
    confirmCalls += 1;
    return json(route, { status: 'confirmed', result: {} });
  });
  await page.route('**/api/actions/act-cancel-2/cancel', (route) => json(route, { status: 'cancelled' }));

  await page.goto('/');
  const input = page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...');
  await input.fill('hủy đơn SL-CAN002');
  await input.press('Enter');
  await page.getByRole('button', { name: 'Hủy', exact: true }).click();
  await expect(page.getByText('Đề xuất đã bị hủy.')).toBeVisible();
  expect(confirmCalls).toBe(0);
});
