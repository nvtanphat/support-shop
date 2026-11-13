import {
  Message,
  OrderDetail,
  OrderListItem,
  PendingAction,
  PolicyDetail,
  PolicySummary,
  ApprovalRequest,
  StaffMetrics,
  Ticket,
} from './types';

const API_BASE = '/api';

class ApiClient {
  private token: string | null = null;
  private guestToken: string | null = null;

  constructor() {
    this.token = localStorage.getItem('token');
    this.guestToken = localStorage.getItem('guest_token');
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
  }

  setGuestToken(token: string | null) {
    this.guestToken = token;
    if (token) {
      localStorage.setItem('guest_token', token);
    } else {
      localStorage.removeItem('guest_token');
    }
  }

  getToken() {
    return this.token;
  }

  /** Who is signed in, for the header. Only the email's local part is kept (no other profile data). */
  getProfile(): { kind: 'customer' | 'staff'; label: string } | null {
    if (!this.token) return null;
    try {
      const raw = localStorage.getItem('session_profile');
      return raw ? JSON.parse(raw) : { kind: 'customer', label: 'Tài khoản' };
    } catch {
      return { kind: 'customer', label: 'Tài khoản' };
    }
  }

  private setProfile(kind: 'customer' | 'staff', email: string) {
    localStorage.setItem('session_profile', JSON.stringify({ kind, label: email.split('@')[0] || 'Tài khoản' }));
  }

  getGuestToken() {
    return this.guestToken;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers || {});
    if (this.token) {
      headers.set('Authorization', `Bearer ${this.token}`);
    }
    if (this.guestToken) {
      headers.set('X-Guest-Token', this.guestToken);
    }
    if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }

    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorDetail = 'Lỗi hệ thống';
      try {
        const errJson = await response.json();
        errorDetail = errJson.detail || errJson.error?.message || response.statusText;
      } catch {
        // Fallback
      }
      throw new Error(errorDetail);
    }

    return response.json();
  }

  // --- Auth ---
  async login(email: string, password: string):Promise<{ access_token: string; role: string }> {
    const res = await this.request<{ access_token: string; role: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(res.access_token);
    this.setProfile('customer', email);
    return res;
  }

  async staffLogin(email: string, password: string): Promise<{ access_token: string; role: string }> {
    const res = await this.request<{ access_token: string; role: string }>('/staff/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(res.access_token);
    this.setProfile('staff', email);
    return res;
  }

  logout() {
    this.setToken(null);
    this.setGuestToken(null);
    localStorage.removeItem('session_profile');
  }

  // --- Guest Verification ---
  async requestGuestVerification(orderCode: string, phone: string) {
    return this.request<{ verification_id: string; message: string; simulated_otp?: string }>('/guest/verifications', {
      method: 'POST',
      body: JSON.stringify({ order_code: orderCode, phone }),
    });
  }

  async verifyGuestOtp(verificationId: string, otp: string) {
    const res = await this.request<{ status: string; guest_token?: string; expires_in?: number; message?: string }>(
      `/guest/verifications/${verificationId}/otp`,
      {
        method: 'POST',
        body: JSON.stringify({ otp }),
      }
    );
    if (res.guest_token) {
      this.setGuestToken(res.guest_token);
    }
    return res;
  }

  // --- Conversations ---
  async createConversation() {
    const res = await this.request<{
      id: string;
      conversation_id?: string;
      guest_token?: string;
      mode: string;
    }>('/conversations', {
      method: 'POST',
      body: JSON.stringify({ channel: 'web' }),
    });
    if (res.guest_token) {
      this.setGuestToken(res.guest_token);
    }
    return {
      conversation_id: res.conversation_id || res.id,
      id: res.id || res.conversation_id || '',
      guest_token: res.guest_token,
      mode: res.mode,
    };
  }

  async getConversation(id: string) {
    return this.request<{
      id: string;
      mode: string;
      messages: Message[];
      pending_actions: PendingAction[];
    }>(`/conversations/${id}`);
  }

  async getOrder(orderCode: string) {
    return this.request<OrderDetail>(`/orders/${encodeURIComponent(orderCode)}`);
  }

  // --- Policies (public, current version) ---
  async getPolicies() {
    return this.request<{ policies: PolicySummary[] }>('/policies');
  }

  async getPolicy(clauseId: string) {
    return this.request<PolicyDetail>(`/policies/${encodeURIComponent(clauseId)}`);
  }

  async sendMessage(conversationId: string, content: string, turnId?: string) {
    const headers: Record<string, string> = {};
    if (turnId) {
      headers['X-Idempotency-Key'] = turnId;
    }
    const res = await this.request<{
      status: string;
      verified_output?: string;
      assistant_message?: string;
      citations?: string[];
      pending_action?: PendingAction;
      tool_calls?: any[];
      ticket_code?: string;
      message?: string;
    }>(`/conversations/${conversationId}/messages`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ content, idempotency_key: turnId }),
    });
    return {
      ...res,
      assistant_message: res.assistant_message || res.verified_output || res.message,
    };
  }

  async handoff(conversationId: string, reasonCode: string, summary: string) {
    return this.request<{ status: string; ticket_code: string }>(
      `/conversations/${conversationId}/handoff`,
      {
        method: 'POST',
        body: JSON.stringify({ reason_code: reasonCode, summary }),
      }
    );
  }

  // --- Actions ---
  async confirmAction(actionId: string, previewHash: string) {
    return this.request<{ status: string; result: Record<string, any> }>(
      `/actions/${actionId}/confirm`,
      {
        method: 'POST',
        body: JSON.stringify({ preview_hash: previewHash }),
      }
    );
  }

  async cancelAction(actionId: string) {
    return this.request<{ status: string }>(`/actions/${actionId}/cancel`, {
      method: 'POST',
    });
  }

  async uploadEvidence(returnCode: string, files: File[]) {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));

    return this.request<{ uploaded_count: number }>(`/returns/${returnCode}/evidence`, {
      method: 'POST',
      body: formData,
    });
  }

  // --- Customer Data ---
  async getMyOrders(): Promise<{ orders: OrderListItem[] }> {
    return this.request<{ orders: OrderListItem[] }>('/me/orders');
  }

  // --- Staff Workstation ---
  async listApprovals(gate?: string, status: string = 'pending'): Promise<{ approvals: ApprovalRequest[] }> {
    const params = new URLSearchParams({ status });
    if (gate) params.append('gate', gate);
    return this.request<{ approvals: ApprovalRequest[] }>(`/staff/approvals?${params.toString()}`);
  }

  async decideApproval(approvalId: string, decision: 'approve' | 'reject', note: string) {
    return this.request<{ status: string }>(`/staff/approvals/${approvalId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, note }),
    });
  }

  async listTickets(status: string = 'open'): Promise<{ tickets: Ticket[] }> {
    return this.request<{ tickets: Ticket[] }>(`/staff/tickets?status=${status}`);
  }

  async claimTicket(ticketId: string) {
    return this.request<{ status: string; ticket_code: string }>(`/staff/tickets/${ticketId}/claim`, {
      method: 'POST',
    });
  }

  async sendStaffMessage(conversationId: string, content: string) {
    return this.request<{ status: string }>(`/staff/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  }

  async returnToAi(conversationId: string) {
    return this.request<{ status: string }>(`/staff/conversations/${conversationId}/return-to-ai`, {
      method: 'POST',
    });
  }

  async staffMetrics(): Promise<StaffMetrics> {
    return this.request<StaffMetrics>('/staff/metrics');
  }

  async sandboxAdvanceShipment(trackingCode: string) {
    return this.request<{ tracking_code: string; status: string }>(
      `/sandbox/shipments/${encodeURIComponent(trackingCode)}/advance`,
      { method: 'POST' }
    );
  }

  async sandboxFailNextPayment() {
    return this.request<{ status: string }>('/sandbox/payments/fail-next', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  }
}

export const api = new ApiClient();
