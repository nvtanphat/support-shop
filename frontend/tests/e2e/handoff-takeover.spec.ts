import { expect, test } from '@playwright/test';
import { json, mockConversation, signInAsStaff } from './helpers';

test('customer asks for a person, staff take over, reply and hand the conversation back', async ({ page, context }) => {
  const conv = 'conv-handoff';
  let handoffCalls = 0;
  await mockConversation(page, conv);
  await page.route(`**/api/conversations/${conv}/handoff`, (route) => {
    handoffCalls += 1;
    return json(route, { status: 'waiting_human', ticket_code: 'TK-HAND01' });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Liên hệ' }).click();
  await expect(page.getByPlaceholder('Nhân viên đang tiếp nhận cuộc trò chuyện này...')).toBeVisible();
  expect(handoffCalls).toBe(1);

  const staff = await context.newPage();
  await signInAsStaff(staff);
  const calls: string[] = [];
  let sent: { content?: string } = {};
  await staff.route('**/api/conversations', (route) => json(route, { id: 'x', conversation_id: 'x', guest_token: 'g', mode: 'ai' }));
  await staff.route('**/api/staff/approvals?*', (route) => json(route, { approvals: [] }));
  await staff.route('**/api/staff/tickets?*', (route) =>
    json(route, {
      tickets: [
        { id: 'tk-1', code: 'TK-HAND01', conversation_id: conv, status: 'open', priority: 'high', reason_code: 'customer_request', summary: 'Khách muốn gặp nhân viên', assigned_to: null, created_at: new Date().toISOString() },
      ],
    })
  );
  await staff.route('**/api/staff/tickets/tk-1/claim', (route) => {
    calls.push('claim');
    return json(route, { status: 'claimed', ticket_code: 'TK-HAND01' });
  });
  await staff.route(`**/api/staff/conversations/${conv}/messages`, (route) => {
    calls.push('message');
    sent = route.request().postDataJSON();
    return json(route, { status: 'sent', seq: 1 });
  });
  await staff.route(`**/api/staff/conversations/${conv}/return-to-ai`, (route) => {
    calls.push('return');
    return json(route, { status: 'returned_to_ai', mode: 'ai' });
  });

  await staff.goto('/');
  await staff.getByRole('button', { name: 'Nhân viên' }).click();
  await staff.getByRole('button', { name: /Phiếu & Hội thoại/ }).click();
  await expect(staff.getByText('TK-HAND01')).toBeVisible();
  await staff.getByRole('button', { name: /Tiếp nhận phiếu này/ }).click();
  await expect.poll(() => calls).toContain('claim');

  await staff.getByText('TK-HAND01').first().click();
  await staff.getByPlaceholder('Nhập phản hồi trực tiếp tới khách hàng...').fill('Chào anh/chị, em là nhân viên hỗ trợ.');
  await staff.getByRole('button', { name: 'Gửi' }).click();
  await expect.poll(() => sent.content).toBe('Chào anh/chị, em là nhân viên hỗ trợ.');
  await staff.getByRole('button', { name: 'Trả hội thoại về cho AI' }).click();
  await expect.poll(() => calls).toEqual(['claim', 'message', 'return']);
});
