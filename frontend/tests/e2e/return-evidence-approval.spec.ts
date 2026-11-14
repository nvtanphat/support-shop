import { expect, test } from '@playwright/test';
import { json, mockConversation, pendingAction, signInAsStaff } from './helpers';

test('a return that needs evidence: customer uploads it, then staff approve with a note', async ({ page, context }) => {
  const conv = 'conv-evidence';
  let uploaded = false;
  await mockConversation(page, conv);
  await page.route(`**/api/conversations/${conv}/messages`, (route) =>
    json(route, {
      status: 'success',
      assistant_message: 'Sản phẩm lỗi cần bằng chứng. Quý khách xác nhận để tạo yêu cầu.',
      citations: [],
      pending_action: pendingAction(conv, {
        id: 'act-evid',
        type: 'return',
        title: 'Đề xuất trả hàng SL-EVD001',
        description: 'Lý do: sản phẩm lỗi',
        extra: { requires_evidence: true, requires_approval: true },
      }),
    })
  );
  await page.route('**/api/actions/act-evid/confirm', (route) =>
    json(route, { status: 'confirmed', result: { return_code: 'RT-EVD001', requires_evidence: true } })
  );
  await page.route('**/api/returns/RT-EVD001/evidence', (route) => {
    uploaded = true;
    return json(route, { uploaded_count: 1 });
  });

  await page.goto('/');
  const input = page.getByPlaceholder('Nhập câu hỏi hoặc yêu cầu hỗ trợ...');
  await input.fill('trả hàng SL-EVD001 vì lỗi');
  await input.press('Enter');
  await expect(page.getByText('Yêu cầu cung cấp bằng chứng hình ảnh/video')).toBeVisible();
  await page.getByRole('button', { name: 'Xác nhận' }).click();
  await page.getByRole('button', { name: /Tải lên bằng chứng/ }).click();
  await expect(page.getByText('Yêu cầu trả hàng: RT-EVD001', { exact: true })).toBeVisible();
  await page.locator('input[type=file]').setInputFiles({ name: 'loi.png', mimeType: 'image/png', buffer: Buffer.from('89504e470d0a1a0a', 'hex') });
  await page.getByRole('button', { name: /Hoàn tất tải lên \(1\)/ }).click();
  await expect.poll(() => uploaded).toBe(true);

  // Staff side: approve the gate A request.
  const staff = await context.newPage();
  await signInAsStaff(staff);
  let decision: { decision?: string; note?: string } = {};
  await staff.route('**/api/staff/approvals?*', (route) =>
    json(route, {
      approvals: [
        { id: 'apr-1', gate: 'A_return', subject_type: 'return_request', subject_id: 'aaaaaaaa-0000-0000-0000-000000000001', status: 'pending', required_role: 'agent', risk_flags: [], requested_at: new Date().toISOString() },
      ],
    })
  );
  await staff.route('**/api/staff/approvals/apr-1/decision', async (route) => {
    decision = route.request().postDataJSON();
    await json(route, { status: 'approved' });
  });
  await staff.route('**/api/conversations', (route) => json(route, { id: 'x', conversation_id: 'x', guest_token: 'g', mode: 'ai' }));
  await staff.goto('/');
  await staff.getByRole('button', { name: 'Nhân viên' }).click();
  await expect(staff.getByText('Cổng: A_return')).toBeVisible();
  await staff.getByRole('button', { name: /Xem xét/ }).click();
  await staff.getByPlaceholder('Nhập lý do duyệt hoặc lý do từ chối...').fill('Ảnh khớp với mô tả lỗi');
  await staff.getByRole('button', { name: /Chấp thuận/ }).click();
  await expect.poll(() => decision.decision).toBe('approve');
  expect(decision.note).toBe('Ảnh khớp với mô tả lỗi');
});
