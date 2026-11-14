import { test, expect } from '@playwright/test';

test.describe('Order Lookup Journey', () => {
  test('customer queries order status in chat', async ({ page }) => {
    await page.route('**/api/conversations', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'conv-test-order',
            conversation_id: 'conv-test-order',
            guest_token: 'gst_test_order_token',
            mode: 'ai',
          }),
        });
      } else {
        await route.continue();
      }
    });

    await page.route('**/api/conversations/conv-test-order', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'conv-test-order',
          mode: 'ai',
          messages: [],
          pending_actions: [],
        }),
      });
    });

    await page.route('**/api/conversations/conv-test-order/events*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: ': keep-alive\n\n',
      });
    });

    await page.route('**/api/conversations/conv-test-order/messages', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          assistant_message: 'Đơn hàng SL-8F3D9K hiện có trạng thái: Đã giao hàng thành công. Tổng giá trị đơn: 1.250.000 đ.',
          citations: [],
        }),
      });
    });

    await page.goto('/');

    const chatInput = page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...');
    await expect(chatInput).toBeVisible();
    await chatInput.fill('Kiểm tra trạng thái đơn hàng SL-8F3D9K giúp tôi');
    await chatInput.press('Enter');

    await expect(page.getByText('Kiểm tra trạng thái đơn hàng SL-8F3D9K giúp tôi')).toBeVisible();
    await expect(page.getByText('Đơn hàng SL-8F3D9K hiện có trạng thái: Đã giao hàng thành công.')).toBeVisible();
  });
});
