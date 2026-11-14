import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { HeroBanner } from '../../src/features/chat/components/HeroBanner';
import { MessageItem } from '../../src/features/chat/components/MessageItem';
import { OrderContextSidebar, relatedPolicies } from '../../src/features/chat/components/OrderContextSidebar';
import { GuestOtpModal } from '../../src/features/chat/GuestOtpModal';
import { api } from '../../src/lib/api';
import { clearOrderCache } from '../../src/lib/useOrder';
import { canRequestReturn, formatDate, formatVnd, orderCodesIn, timelineFor } from '../../src/lib/orderView';
import type { OrderDetail, PolicySummary } from '../../src/lib/types';

const order: OrderDetail = {
  order_id: 'o1',
  order_code: 'SL-ABC123',
  status: 'delivered',
  payment_method: 'ewallet',
  total: 700000,
  placed_at: '2026-11-08T09:00:00+07:00',
  delivered_at: '2026-11-10T15:00:00+07:00',
  items: [
    { item_id: 'i1', product_name: 'Áo sơ mi', qty: 1, unit_price: 300000 },
    { item_id: 'i2', product_name: 'Quần jean', qty: 1, unit_price: 400000 },
  ],
  available_actions: [{ action: 'return', type: 'eligible_check', label: 'Trả hàng' }],
};

const policies: PolicySummary[] = [
  { clause_id: 'POL-RETURN-01', topic: 'return', title: 'Đổi trả do lỗi', version: 'v1', effective_from: '2026-11-01T00:00:00Z', effective_to: null },
  { clause_id: 'POL-SHIP-01', topic: 'shipping', title: 'Vận chuyển', version: 'v1', effective_from: '2026-11-01T00:00:00Z', effective_to: null },
];

afterEach(() => {
  vi.restoreAllMocks();
  clearOrderCache();
});

describe('order view helpers', () => {
  it('finds order codes in free text without duplicates', () => {
    expect(orderCodesIn('Đơn sl-abc123 và SL-ABC123, còn SL-XYZ9?')).toEqual(['SL-ABC123', 'SL-XYZ9']);
    expect(orderCodesIn('Không có mã đơn')).toEqual([]);
  });

  it('formats money and dates the Vietnamese way', () => {
    expect(formatVnd(1290000)).toBe('1.290.000 ₫');
    expect(formatDate('2026-11-08T09:00:00+07:00')).toBe('08/11/2026');
    expect(formatDate(null)).toBe('');
  });

  it('derives the timeline from status and never invents dates', () => {
    const steps = timelineFor({ status: 'packing', placed_at: order.placed_at, delivered_at: null })!;
    expect(steps.map((s) => s.reached)).toEqual([true, true, false, false]);
    expect(steps[0].date).toBe('08/11');
    expect(steps[1].date).toBe('');
    expect(steps[3].date).toBe('');
    expect(timelineFor({ status: 'cancelled', placed_at: null, delivered_at: null })).toBeNull();
  });

  it('offers a return only when the order says so', () => {
    expect(canRequestReturn(order)).toBe(true);
    expect(canRequestReturn({ available_actions: [{ action: 'cancel', type: 'self_service', label: 'Hủy' }] })).toBe(false);
    expect(canRequestReturn({})).toBe(false);
  });
});

describe('HeroBanner', () => {
  it('sends generic prompts that name no order', () => {
    const onPrompt = vi.fn();
    render(<HeroBanner onQuickPrompt={onPrompt} />);
    fireEvent.click(screen.getByText('Đổi trả / Hoàn tiền'));
    fireEvent.click(screen.getByText('Tra cứu đơn hàng'));
    const prompts = onPrompt.mock.calls.map((c) => c[0] as string);
    expect(prompts).toEqual(['Mình muốn đổi trả / hoàn tiền', 'Tra cứu đơn hàng của tôi']);
    expect(prompts.every((p) => orderCodesIn(p).length === 0)).toBe(true);
  });
});

describe('MessageItem', () => {
  const base = { id: 'm1', seq: 1, citations: [] as string[], created_at: '2026-11-11T10:25:00+07:00' };

  it('renders a card built from the fetched order, and policy citations as buttons', async () => {
    vi.spyOn(api, 'getOrder').mockResolvedValue(order);
    const onSelectClause = vi.fn();
    render(
      <MessageItem
        message={{ ...base, role: 'assistant', content: 'Đơn **SL-ABC123** còn hạn theo [POL-RETURN-01].' }}
        onSelectClause={onSelectClause}
        onQuickPrompt={() => {}}
        onViewPolicy={() => {}}
      />
    );
    expect(await screen.findByText('Áo sơ mi và 1 sản phẩm khác')).toBeInTheDocument();
    expect(screen.getByText('700.000 ₫')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '[POL-RETURN-01]' }));
    expect(onSelectClause).toHaveBeenCalledWith('POL-RETURN-01');
    expect(screen.getByText('Tạo yêu cầu đổi trả')).toBeInTheDocument();
  });

  it('shows no card when the order cannot be loaded', async () => {
    const getOrder = vi.spyOn(api, 'getOrder').mockRejectedValue(new Error('Không tìm thấy'));
    render(
      <MessageItem
        message={{ ...base, role: 'assistant', content: 'Mình chưa thấy đơn SL-NOPE99.' }}
        onSelectClause={() => {}}
        onQuickPrompt={() => {}}
        onViewPolicy={() => {}}
      />
    );
    await waitFor(() => expect(getOrder).toHaveBeenCalled());
    expect(screen.queryByText('Mã đơn:')).not.toBeInTheDocument();
  });

  it('never fetches orders for a customer message', () => {
    const getOrder = vi.spyOn(api, 'getOrder');
    render(
      <MessageItem
        message={{ ...base, role: 'customer', content: 'Đơn SL-ABC123 sao rồi?' }}
        onSelectClause={() => {}}
        onQuickPrompt={() => {}}
        onViewPolicy={() => {}}
      />
    );
    expect(getOrder).not.toHaveBeenCalled();
  });
});

describe('OrderContextSidebar', () => {
  const props = {
    policies: { status: 'ready' as const, policies },
    citedClauseIds: [] as string[],
    isGuest: false,
    onQuickPrompt: () => {},
    onSelectClause: () => {},
    onOpenOtp: () => {},
  };

  it('asks for an order code instead of showing a sample order', () => {
    render(<OrderContextSidebar {...props} orderCode={null} />);
    expect(screen.getByText(/Chưa có đơn hàng nào được chọn/)).toBeInTheDocument();
  });

  it('shows the real order with its items and payment method', async () => {
    vi.spyOn(api, 'getOrder').mockResolvedValue(order);
    render(<OrderContextSidebar {...props} orderCode="SL-ABC123" />);
    expect(await screen.findByText('Đơn hàng SL-ABC123')).toBeInTheDocument();
    expect(screen.getByText('Quần jean')).toBeInTheDocument();
    expect(screen.getByText('Ví điện tử')).toBeInTheDocument();
    expect(screen.getByText('Đã giao')).toBeInTheDocument();
  });

  it('tells a guest how to unlock an order that could not be loaded', async () => {
    vi.spyOn(api, 'getOrder').mockRejectedValue(new Error('Bạn không có quyền'));
    render(<OrderContextSidebar {...props} orderCode="SL-ABC123" isGuest />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Bạn không có quyền');
    expect(screen.getByText('Xác thực OTP tra cứu')).toBeInTheDocument();
  });

  it('lists cited clauses first, else the return rules', () => {
    expect(relatedPolicies(policies, ['POL-SHIP-01']).map((p) => p.clause_id)).toEqual(['POL-SHIP-01']);
    expect(relatedPolicies(policies, []).map((p) => p.clause_id)).toEqual(['POL-RETURN-01']);
    expect(relatedPolicies(policies, ['POL-GONE-00'])).toHaveLength(1); // unknown citation falls back
  });
});

describe('GuestOtpModal', () => {
  it('opens empty, or with the order under discussion, never with sample values', () => {
    const { rerender } = render(<GuestOtpModal isOpen onClose={() => {}} onVerified={() => {}} />);
    expect(screen.getByPlaceholderText('Ví dụ: SL-XXXXXX')).toHaveValue('');
    expect(screen.getByPlaceholderText('Số điện thoại dùng khi đặt hàng')).toHaveValue('');
    rerender(<GuestOtpModal isOpen onClose={() => {}} onVerified={() => {}} defaultOrderCode="SL-ABC123" />);
    expect(screen.getByPlaceholderText('Ví dụ: SL-XXXXXX')).toHaveValue('SL-ABC123');
  });
});

describe('no demo data in the interface source', () => {
  const sources = import.meta.glob('../../src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
  const forbidden = ['SL-8F3D9K', 'Tai nghe không dây', 'Studio Pro', 'Lan Nguyễn', 'Khách hàng VIP', 'SecurePass', 'lan.nguyen', '17/11/2026', 'POL-RET-ELIG'];

  it.each(forbidden)('does not contain %s', (needle) => {
    const offenders = Object.entries(sources).filter(([, text]) => text.includes(needle)).map(([file]) => file);
    expect(offenders).toEqual([]);
  });
});
