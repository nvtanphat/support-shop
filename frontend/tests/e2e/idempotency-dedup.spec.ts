import { test, expect } from '@playwright/test';

test.describe('Idempotency & Message Deduplication', () => {
  test('ensures X-Idempotency-Key is sent and prevents duplicate message bubbles', async ({ page }) => {
    let capturedIdempotencyHeader: string | null = null;
    let capturedBodyTurnId: string | null = null;

    await page.route('**/api/conversations', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'conv-test-idemp',
            conversation_id: 'conv-test-idemp',
            guest_token: 'gst_test_idemp',
            mode: 'ai',
          }),
        });
      } else {
        await route.continue();
      }
    });

    await page.route('**/api/conversations/conv-test-idemp', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'conv-test-idemp',
          mode: 'ai',
          messages: [],
          pending_actions: [],
        }),
      });
    });

    // Provide an SSE event stream that delivers a message.completed event
    await page.route('**/api/conversations/conv-test-idemp/events*', async (route) => {
      const sseContent = [
        'event: message.completed\n',
        'data: ' + JSON.stringify({
          id: 'asst-msg-canonical-001',
          seq: 2,
          role: 'assistant',
          content: 'Xin chào, em có thể hỗ trợ gì cho đơn hàng của quý khách?',
          citations: [],
        }) + '\n\n',
      ].join('');

      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseContent,
      });
    });

    await page.route('**/api/conversations/conv-test-idemp/messages', async (route) => {
      const headers = route.request().headers();
      capturedIdempotencyHeader = headers['x-idempotency-key'] || null;

      const postData = route.request().postDataJSON();
      capturedBodyTurnId = postData?.idempotency_key || null;

      // Also return the assistant message in POST response
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          assistant_message: 'Xin chào, em có thể hỗ trợ gì cho đơn hàng của quý khách?',
          citations: [],
        }),
      });
    });

    await page.goto('/');

    const chatInput = page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...');
    await chatInput.fill('Xin chào shop');
    await chatInput.press('Enter');

    // Wait for the assistant bubble to be rendered
    const assistantBubbles = page.locator('text=Xin chào, em có thể hỗ trợ gì cho đơn hàng của quý khách?');
    await expect(assistantBubbles).toBeVisible();

    // Verify deduplication: There must be EXACTLY ONE assistant bubble with this text, not duplicates!
    await expect(assistantBubbles).toHaveCount(1);

    // Verify idempotency headers were properly passed
    expect(capturedIdempotencyHeader).toBeTruthy();
    expect(capturedBodyTurnId).toBeTruthy();
    expect(capturedIdempotencyHeader).toBe(capturedBodyTurnId);
  });
});
