import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import { expect, test } from '@playwright/test';
import { json } from './helpers';

const message = (seq: number, content: string) =>
  `id: ${seq}\nevent: message.completed\ndata: ${JSON.stringify({ id: `m-${seq}`, seq, role: 'assistant', content, citations: [] })}\n\n`;

test('after the stream drops the client reconnects with Last-Event-ID and shows each message once', async ({ page }) => {
  const conv = 'conv-reconnect';
  const seen: (string | undefined)[] = [];

  // A real SSE endpoint: the browser adds Last-Event-ID itself, which route.fulfill cannot show us.
  const server = createServer((req, res) => {
    const lastEventId = req.headers['last-event-id'];
    seen.push(Array.isArray(lastEventId) ? lastEventId[0] : lastEventId);
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-cache' });
    // The first connection delivers message 1 and then ends (network lost); the reconnect resumes after it.
    res.end(lastEventId ? `retry: 200\n${message(2, 'Tin nhắn thứ hai sau khi nối lại')}` : `retry: 200\n${message(1, 'Tin nhắn thứ nhất')}`);
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = (server.address() as AddressInfo).port;

  try {
    await page.route('**/api/conversations', (route) =>
      route.request().method() === 'POST' ? json(route, { id: conv, conversation_id: conv, guest_token: 'gst_rc', mode: 'ai' }) : route.continue()
    );
    // The detail endpoint reflects what the server has persisted, as the real one does.
    await page.route(`**/api/conversations/${conv}`, (route) =>
      json(route, {
        id: conv,
        mode: 'ai',
        messages: [
          ...(seen.length >= 1 ? [{ id: 'm-1', seq: 1, role: 'assistant', content: 'Tin nhắn thứ nhất', citations: [], created_at: new Date().toISOString() }] : []),
          ...(seen.length >= 2 ? [{ id: 'm-2', seq: 2, role: 'assistant', content: 'Tin nhắn thứ hai sau khi nối lại', citations: [], created_at: new Date().toISOString() }] : []),
        ],
        pending_actions: [],
      })
    );
    await page.route(`**/api/conversations/${conv}/events*`, (route) => route.continue({ url: `http://127.0.0.1:${port}/events` }));

    await page.goto('/');
    await expect(page.getByText('Tin nhắn thứ nhất')).toBeVisible();
    await expect(page.getByText('Tin nhắn thứ hai sau khi nối lại')).toBeVisible({ timeout: 10000 });
    expect(seen[0]).toBeUndefined();
    expect(seen.slice(1)).toContain('1');
    await expect(page.getByText('Tin nhắn thứ nhất')).toHaveCount(1);
  } finally {
    server.closeAllConnections();
    server.close();
  }
});
