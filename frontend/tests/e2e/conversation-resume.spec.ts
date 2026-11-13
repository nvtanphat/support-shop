import { expect, test } from '@playwright/test';
import { json } from './helpers';

test('reloading the page resumes the same conversation instead of starting an empty one', async ({ page }) => {
  let created = 0;
  await page.route('**/api/conversations', (route) => {
    created += 1;
    return json(route, { id: 'conv-resume', conversation_id: 'conv-resume', guest_token: 'gst_resume', mode: 'ai' });
  });
  await page.route('**/api/conversations/conv-resume', (route) =>
    json(route, {
      id: 'conv-resume',
      mode: 'ai',
      messages: [
        { id: 'm1', seq: 1, role: 'customer', content: 'Đơn SL-RES001 của mình đâu rồi?', citations: [] },
        { id: 'm2', seq: 2, role: 'assistant', content: 'Đơn đang được giao.', citations: [] },
      ],
      pending_actions: [],
    })
  );
  await page.route('**/api/conversations/conv-resume/events*', (route) =>
    route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': idle\n\n' })
  );

  await page.goto('/');
  await expect(page.getByText('Đơn đang được giao.')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Đơn đang được giao.')).toBeVisible();
  expect(created).toBe(1);
});
