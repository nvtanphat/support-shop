import { expect, test } from '@playwright/test';
import { json } from './helpers';

const jwt = (expSeconds: number) =>
  `h.${Buffer.from(JSON.stringify({ sub: 'c1', role: 'customer', exp: expSeconds })).toString('base64url')}.s`;

test('an expired token left from an earlier visit is dropped instead of breaking every call', async ({ page }) => {
  await page.addInitScript((token) => {
    localStorage.setItem('token', token);
    localStorage.setItem('session_profile', JSON.stringify({ kind: 'customer', label: 'old' }));
  }, jwt(Math.floor(Date.now() / 1000) - 60));
  let authHeader: string | undefined = 'not-called';
  await page.route('**/api/conversations', (route) => {
    authHeader = route.request().headers()['authorization'];
    return json(route, { id: 'conv-x', conversation_id: 'conv-x', guest_token: 'g', mode: 'ai' });
  });
  await page.route('**/api/conversations/conv-x*', (route) => json(route, { id: 'conv-x', mode: 'ai', messages: [], pending_actions: [] }));
  await page.goto('/');
  await expect.poll(() => authHeader).toBeUndefined();
  await expect(page.getByRole('button', { name: 'Đăng nhập' })).toBeVisible();
});

test('a 401 during the session signs out, asks to log in again and keeps the chat usable as a guest', async ({ page }) => {
  await page.addInitScript((token) => {
    localStorage.setItem('token', token);
    localStorage.setItem('session_profile', JSON.stringify({ kind: 'customer', label: 'me' }));
  }, jwt(Math.floor(Date.now() / 1000) + 3600));
  let calls = 0;
  await page.route('**/api/conversations', (route) => {
    calls += 1;
    if (route.request().headers()['authorization']) return json(route, { detail: 'Token không hợp lệ hoặc đã hết hạn.' }, 401);
    return json(route, { id: 'conv-g', conversation_id: 'conv-g', guest_token: 'g', mode: 'ai' });
  });
  await page.route('**/api/conversations/conv-g*', (route) => json(route, { id: 'conv-g', mode: 'ai', messages: [], pending_actions: [] }));
  await page.route('**/api/me/orders*', (route) => json(route, { detail: 'expired' }, 401));
  await page.goto('/');
  await expect(page.getByText('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.')).toBeVisible();
  await expect.poll(() => calls).toBeGreaterThanOrEqual(2); // retried as a guest
});
