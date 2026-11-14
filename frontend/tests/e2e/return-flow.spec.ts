import { test, expect } from '@playwright/test';

test.describe('Return Flow Journey', () => {
  test('proposes return action and confirms request', async ({ page }) => {
    const actionId = 'act-test-ret-001';

    await page.route('**/api/conversations', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'conv-test-return',
            conversation_id: 'conv-test-return',
            guest_token: 'gst_test_return_token',
            mode: 'ai',
          }),
        });
      } else {
        await route.continue();
      }
    });

    await page.route('**/api/conversations/conv-test-return', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'conv-test-return',
          mode: 'ai',
          messages: [],
          pending_actions: [],
        }),
      });
    });

    await page.route('**/api/conversations/conv-test-return/events*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: ': keep-alive\n\n',
      });
    });

    await page.route('**/api/conversations/conv-test-return/messages', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          assistant_message: 'Em đã lập phiếu đề xuất đổi trả cho đơn SL-8F3D9K. Quý khách vui lòng xác nhận bên dưới.',
          citations: ['POL-RET-ELIG'],
          pending_action: {
            id: actionId,
            action_id: actionId,
            conversation_id: 'conv-test-return',
            type: 'return',
            payload_hash: 'hash-test-return-12345',
            preview: {
              title: 'Đề xuất đổi trả đơn hàng SL-8F3D9K',
              description: 'Lý do: Tai nghe bị rè âm thanh',
              order_code: 'SL-8F3D9K',
              estimated_refund_vnd: 450000,
            },
            status: 'proposed',
            presented_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
          },
        }),
      });
    });

    // Mock confirm action
    await page.route(`**/api/actions/${actionId}/confirm`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'confirmed',
          result: {
            return_code: 'RET-202611-001',
            status: 'pending_warehouse',
          },
        }),
      });
    });

    await page.goto('/');

    const chatInput = page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...');
    await chatInput.fill('Mình muốn đổi trả đơn hàng SL-8F3D9K do lỗi tai nghe');
    await chatInput.press('Enter');

    // Wait for proposed action card
    await expect(page.getByText('Đề xuất đổi trả đơn hàng SL-8F3D9K')).toBeVisible();
    await expect(page.getByText('Khoản hoàn ước tính:')).toBeVisible();

    // Click confirm button
    const confirmBtn = page.getByRole('button', { name: 'Xác nhận' });
    await expect(confirmBtn).toBeVisible();
    await confirmBtn.click();

    // Verify confirmed state
    await expect(page.getByText('Đã xác nhận thành công!')).toBeVisible();
    await expect(page.getByText('RET-202611-001')).toBeVisible();
  });
});
