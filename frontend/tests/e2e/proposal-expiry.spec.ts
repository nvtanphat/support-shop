import { expect, test } from '@playwright/test';
import { json, mockConversation, pendingAction } from './helpers';

test('an expired proposal cannot be confirmed and a new one can be requested', async ({ page }) => {
  const conv = 'conv-expiry';
  let turn = 0;
  await mockConversation(page, conv);
  await page.route(`**/api/conversations/${conv}/messages`, (route) => {
    turn += 1;
    const first = turn === 1;
    return json(route, {
      status: 'success',
      assistant_message: first ? 'Em đã lập đề xuất hủy đơn SL-EXP001.' : 'Em đã lập lại đề xuất mới.',
      citations: [],
      pending_action: pendingAction(conv, {
        id: first ? 'act-old' : 'act-new',
        type: 'cancel_order',
        title: first ? 'Đề xuất cũ SL-EXP001' : 'Đề xuất mới SL-EXP001',
        description: 'Hủy đơn',
        expiresInMs: first ? 1500 : undefined,
      }),
    });
  });
  await page.route('**/api/actions/act-new/confirm', (route) => json(route, { status: 'confirmed', result: {} }));

  await page.goto('/');
  const input = page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...');
  await input.fill('hủy đơn SL-EXP001');
  await input.press('Enter');
  await expect(page.getByText('Đề xuất cũ SL-EXP001')).toBeVisible();

  await expect(page.getByText('Đề xuất đã hết hạn hiệu lực.')).toBeVisible({ timeout: 6000 });
  await expect(page.getByRole('button', { name: 'Xác nhận' })).toHaveCount(0);

  await input.fill('hủy đơn SL-EXP001 giúp mình lại');
  await input.press('Enter');
  await expect(page.getByText('Đề xuất mới SL-EXP001')).toBeVisible();
  await page.getByRole('button', { name: 'Xác nhận' }).click();
  await expect(page.getByText('Đã xác nhận thành công!')).toBeVisible();
});
