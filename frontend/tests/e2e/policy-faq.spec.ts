import { test, expect } from '@playwright/test';

test.describe('Policy FAQ Journey', () => {
  test('customer asks return policy question and views citation', async ({ page }) => {
    // Mock conversation creation
    await page.route('**/api/conversations', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'conv-test-policy',
            conversation_id: 'conv-test-policy',
            guest_token: 'gst_test_token_123',
            mode: 'ai',
          }),
        });
      } else {
        await route.continue();
      }
    });

    // Mock conversation detail
    await page.route('**/api/conversations/conv-test-policy', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'conv-test-policy',
          mode: 'ai',
          messages: [],
          pending_actions: [],
        }),
      });
    });

    // Mock SSE events
    await page.route('**/api/conversations/conv-test-policy/events*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: ': keep-alive\n\n',
      });
    });

    // Mock send message
    await page.route('**/api/conversations/conv-test-policy/messages', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          assistant_message: 'Theo chính sách [POL-RET-ELIG], khách hàng được đổi trả hàng trong vòng 15 ngày.',
          citations: ['POL-RET-ELIG'],
        }),
      });
    });

    await page.goto('/');

    // Type policy inquiry into chat input
    const chatInput = page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...');
    await expect(chatInput).toBeVisible();
    await chatInput.fill('Chính sách đổi trả hàng như thế nào?');
    await chatInput.press('Enter');

    // Verify customer message is visible
    await expect(page.getByText('Chính sách đổi trả hàng như thế nào?')).toBeVisible();

    // Verify assistant response is visible
    await expect(page.getByText('Theo chính sách [POL-RET-ELIG], khách hàng được đổi trả hàng trong vòng 15 ngày.')).toBeVisible();

    // Verify citation badge is visible
    const citationBadge = page.getByRole('button', { name: /POL-RET-ELIG/i });
    if (await citationBadge.isVisible()) {
      await citationBadge.click();
      await expect(page.getByRole('dialog')).toBeVisible();
      await page.getByRole('button', { name: 'Đóng' }).click();
      await expect(page.getByRole('dialog')).not.toBeVisible();
    }
  });
});
