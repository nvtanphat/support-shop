// Screenshots for README.md. Real API and seeded demo data (run `shopagent.cli seed` first); only the
// assistant's replies are scripted, so no Gemini quota is spent and every shot is reproducible.
//   npm run shots
import { Page, test } from '@playwright/test';
import { json, mockConversation, pendingAction } from '../e2e/helpers';

const OUT = '../docs/images';
const INPUT = 'Nhập câu hỏi hoặc yêu cầu hỗ trợ...';

async function signIn(page: Page, email: string, password: string, staff: boolean) {
  await page.goto('/');
  await page.locator('button.login').click();
  if (staff) await page.getByRole('dialog').getByRole('button', { name: /nhân viên/i }).first().click();
  await page.locator('#login-email').fill(email);
  await page.locator('#login-password').fill(password);
  await page.getByRole('dialog').locator('button[type=submit]').click();
  await page.locator('#login-email').waitFor({ state: 'detached' });
}

async function say(page: Page, conversation: string, text: string, reply: Record<string, unknown>) {
  await page.route(`**/api/conversations/${conversation}/messages`, (r) => json(r, { status: 'success', citations: [], ...reply }));
  const input = page.getByPlaceholder(INPUT);
  await input.fill(text);
  await input.press('Enter');
}

test('policy answer with a citation, then the clause it points to', async ({ page }) => {
  await mockConversation(page, 'shot-policy');
  await page.goto('/');
  await say(page, 'shot-policy', 'Đổi ý trả hàng thì được trong bao nhiêu ngày?', {
    citations: ['POL-RETURN-02'],
    assistant_message:
      'Với hàng không lỗi, bạn có thể đổi ý và trả hàng trong 7 ngày kể từ khi nhận hàng [POL-RETURN-02]. Hàng thuộc danh mục loại trừ như mỹ phẩm đã mở seal thì không áp dụng [POL-RETURN-03].',
  });
  await page.getByText('Với hàng không lỗi').waitFor();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT}/chat-policy.png` });

  await page.locator('button', { hasText: 'POL-RETURN-02' }).first().click();
  await page.getByRole('dialog').waitFor();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT}/citation-modal.png` });
});

test('customer: order card with the real order and its timeline', async ({ page }) => {
  await mockConversation(page, 'shot-order');
  await signIn(page, 'customer1@example.com', 'pass123', false);
  await say(page, 'shot-order', 'Đơn SL-DEMO06 của mình giao tới đâu rồi?', {
    assistant_message: 'Đơn **SL-DEMO06** đã giao thành công. Nếu cần, bạn có thể tạo yêu cầu đổi trả bên dưới.',
  });
  await page.locator('.order-card, [class*="oc"]').first().waitFor({ timeout: 15000 }).catch(() => undefined);
  await page.getByText('Tạo yêu cầu đổi trả').first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(900);
  await page.screenshot({ path: `${OUT}/chat-order.png` });
});

test('customer: return proposal awaiting confirmation', async ({ page }) => {
  await mockConversation(page, 'shot-proposal');
  await signIn(page, 'customer1@example.com', 'pass123', false);
  await say(page, 'shot-proposal', 'Mình muốn trả đơn SL-DEMO11, điện thoại bị lỗi', {
    assistant_message: 'Điện thoại lỗi cần bằng chứng hình ảnh. Bạn xác nhận để tạo yêu cầu trả hàng; tiền hoàn được tính khi kho kiểm hàng.',
    pending_action: pendingAction('shot-proposal', {
      id: 'act-shot',
      type: 'return_request',
      title: 'Xác nhận yêu cầu trả hàng hoàn tiền SL-DEMO11',
      description: 'Lý do: sản phẩm bị lỗi',
      extra: { order_code: 'SL-DEMO11', requires_evidence: true, requires_approval: true, estimated_refund_vnd: 6490000 },
    }),
  });
  await page.getByText('Yêu cầu cung cấp bằng chứng hình ảnh/video').waitFor();
  await page.waitForTimeout(900);
  await page.screenshot({ path: `${OUT}/customer-proposal.png` });
});

test('staff: approval queue, warehouse, takeover and metrics', async ({ page }) => {
  await mockConversation(page, 'shot-staff');
  await signIn(page, 'supervisor@shop.vn', 'staff123', true);
  await page.getByRole('button', { name: 'Nhân viên' }).click();
  await page.getByText(/Cổng:/).first().waitFor();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT}/staff-approvals.png` });

  await page.getByRole('button', { name: /Kho hàng trả về/ }).click();
  await page.getByText(/RT-DEMO/).first().waitFor();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/staff-warehouse.png` });

  await page.getByRole('button', { name: /Phiếu & Hội thoại/ }).click();
  await page.getByText('TK-DEMO01').first().waitFor();
  await page.getByText('TK-DEMO01').first().click();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/staff-takeover.png` });

  await page.getByRole('button', { name: /Vận hành/ }).click();
  await page.getByText(/theo trạng thái/).first().waitFor();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/staff-metrics.png` });
});
