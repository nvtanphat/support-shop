import { test } from '@playwright/test';
import { json, mockConversation, pendingAction } from '../e2e/helpers';

const OUT = '../docs/images';

test('customer: return proposal awaiting confirmation', async ({ page }) => {
  await mockConversation(page, 'c2');
  await page.route('**/api/conversations/c2/messages', (r) =>
    json(r, {
      status: 'success',
      citations: [],
      assistant_message: 'Sản phẩm lỗi cần bằng chứng hình ảnh. Quý khách xác nhận để tạo yêu cầu trả hàng, hệ thống sẽ tính tiền hoàn khi kho kiểm hàng.',
      pending_action: pendingAction('c2', { id: 'act-1', type: 'return', title: 'Đề xuất trả hàng SL-EVD001', description: 'Lý do: sản phẩm lỗi', extra: { requires_evidence: true, requires_approval: true } }),
    })
  );
  await page.goto('/');
  const input = page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...');
  await input.fill('Tôi muốn trả hàng SL-EVD001 vì bị lỗi');
  await input.press('Enter');
  await page.getByText('Yêu cầu cung cấp bằng chứng hình ảnh/video').waitFor();
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/customer-proposal.png` });
});
