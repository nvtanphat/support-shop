import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { EnvironmentBanner } from '../../src/components/EnvironmentBanner';
import { CitationModal } from '../../src/components/CitationModal';
import { ActionCard } from '../../src/features/chat/ActionCard';
import { PendingAction } from '../../src/lib/types';

describe('EnvironmentBanner', () => {
  it('renders simulated mode warning text', () => {
    render(<EnvironmentBanner />);
    expect(screen.getByText(/Môi trường mô phỏng — Không có giao dịch thật/i)).toBeInTheDocument();
  });
});

describe('CitationModal', () => {
  it('renders citation details when clauseId is provided', () => {
    const handleClose = vi.fn();
    render(<CitationModal clauseId="POL-RETURN-01" onClose={handleClose} />);
    expect(screen.getByText('POL-RETURN-01')).toBeInTheDocument();
    expect(screen.getByText(/Điều khoản chính sách ShopLab/i)).toBeInTheDocument();

    const closeBtn = screen.getByLabelText('Đóng');
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('renders null when clauseId is null', () => {
    const { container } = render(<CitationModal clauseId={null} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
  });
});

describe('ActionCard', () => {
  const mockAction: PendingAction = {
    id: 'pa-123',
    conversation_id: 'conv-123',
    type: 'cancel_order',
    payload: { order_code: 'SL-900001' },
    payload_hash: 'abc123hash',
    preview: {
      title: 'Hủy đơn hàng SL-900001',
      description: 'Hủy đơn hàng chưa đóng gói và hoàn tiền 100%.',
      order_code: 'SL-900001',
      estimated_refund_vnd: 250000,
    },
    status: 'proposed',
    presented_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 600000).toISOString(),
  };

  it('renders action card with confirmation buttons and preview information', () => {
    render(<ActionCard action={mockAction} onActionUpdated={() => {}} />);
    expect(screen.getByText('Hủy đơn hàng SL-900001')).toBeInTheDocument();
    expect(screen.getByText('Xác nhận')).toBeInTheDocument();
    expect(screen.getByText('Hủy')).toBeInTheDocument();
    expect(screen.getByText(/250.000 đ/i)).toBeInTheDocument();
  });

  it('renders confirmed status when action is confirmed', () => {
    const confirmedAction: PendingAction = {
      ...mockAction,
      status: 'confirmed',
      result: { status: 'cancelled' },
    };
    render(<ActionCard action={confirmedAction} onActionUpdated={() => {}} />);
    expect(screen.getByText('Đã xác nhận thành công!')).toBeInTheDocument();
    expect(screen.queryByText('Xác nhận')).not.toBeInTheDocument();
  });
});
