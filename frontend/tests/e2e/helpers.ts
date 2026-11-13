import { Page, Route } from '@playwright/test';

export interface ProposedAction {
  id: string;
  type: string;
  title: string;
  description: string;
  expiresInMs?: number;
  extra?: Record<string, unknown>;
}

export const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

export function pendingAction(conversationId: string, a: ProposedAction) {
  return {
    id: a.id,
    action_id: a.id,
    conversation_id: conversationId,
    type: a.type,
    payload_hash: `hash-${a.id}`,
    preview: { title: a.title, description: a.description, ...a.extra },
    status: 'proposed',
    presented_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + (a.expiresInMs ?? 15 * 60 * 1000)).toISOString(),
  };
}

/** Routes for a guest conversation; SSE is an idle stream unless the test overrides it afterwards. */
export async function mockConversation(page: Page, id: string, mode: 'ai' | 'waiting_human' = 'ai') {
  await page.route('**/api/conversations', (route) =>
    route.request().method() === 'POST'
      ? json(route, { id, conversation_id: id, guest_token: `gst_${id}`, mode })
      : route.continue()
  );
  await page.route(`**/api/conversations/${id}`, (route) => json(route, { id, mode, messages: [], pending_actions: [] }));
  await page.route(`**/api/conversations/${id}/events*`, (route) =>
    route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': keep-alive\n\n' })
  );
}

/** Signs in as staff without the login form: the app reads the token and profile from localStorage. */
export async function signInAsStaff(page: Page, role: 'agent' | 'supervisor' = 'agent') {
  await page.addInitScript((r) => {
    localStorage.setItem('token', `staff-token-${r}`);
    localStorage.setItem('session_profile', JSON.stringify({ kind: 'staff', label: r, role: r }));
  }, role);
}
