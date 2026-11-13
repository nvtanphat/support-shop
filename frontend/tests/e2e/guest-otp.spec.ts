import { test, expect } from '@playwright/test';

test.describe('Guest OTP Verification Journey', () => {
  test('guest customer verifies order access via simulated OTP', async ({ page }) => {
    await page.route('**/api/conversations', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'conv-test-otp',
            conversation_id: 'conv-test-otp',
            guest_token: 'gst_init_token',
            mode: 'ai',
          }),
        });
      } else {
        await route.continue();
      }
    });

    await page.route('**/api/conversations/conv-test-otp', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'conv-test-otp',
          mode: 'ai',
          messages: [],
          pending_actions: [],
        }),
      });
    });

    await page.route('**/api/conversations/conv-test-otp/events*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: ': keep-alive\n\n',
      });
    });

    // Mock OTP request
    await page.route('**/api/guest/verifications', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          verification_id: 'v-test-123456',
          message: 'Mã xác thực đã được gửi tới số 0901234567',
          simulated_otp: '654321',
        }),
      });
    });

    // Mock OTP confirm
    await page.route('**/api/guest/verifications/v-test-123456/otp', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'verified',
          guest_token: 'gst_verified_token_789',
          message: 'Xác minh OTP thành công.',
        }),
      });
    });

    await page.goto('/');

    // Click plus button to open OTP modal
    const plusBtn = page.getByTitle('Tra cứu đơn hàng hoặc xác minh OTP');
    await expect(plusBtn).toBeVisible();
    await plusBtn.click();

    // Verify modal header is open
    await expect(page.getByText('Xác minh Đơn hàng Vãng lai')).toBeVisible();

    // Fill and submit the OTP request form (the modal no longer ships prefilled demo values)
    await page.getByPlaceholder('Ví dụ: SL-XXXXXX').fill('SL-TEST01');
    await page.getByPlaceholder('Số điện thoại dùng khi đặt hàng').fill('0900000000');
    const submitRequestBtn = page.getByRole('button', { name: 'Gửi mã OTP qua SMS' });
    await expect(submitRequestBtn).toBeVisible();
    await submitRequestBtn.click();

    // Step 2: Verify OTP
    const verifyOtpBtn = page.getByRole('button', { name: 'Xác thực & Xem đơn' });
    await expect(verifyOtpBtn).toBeVisible();
    await verifyOtpBtn.click();

    // Modal should close on successful verification
    await expect(page.getByText('Xác minh Đơn hàng Vãng lai')).not.toBeVisible();
  });
});
