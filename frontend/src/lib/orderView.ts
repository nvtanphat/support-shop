import type { OrderDetail } from './types';

/** Display helpers for an order. Everything shown comes from the order returned by the API. */

const STATUS_LABEL: Record<string, string> = {
  pending_payment: 'Chờ thanh toán',
  confirmed: 'Đã xác nhận',
  packing: 'Đang đóng gói',
  shipped: 'Đã gửi hàng',
  out_for_delivery: 'Đang giao',
  delivery_failed: 'Giao không thành công',
  delivered: 'Đã giao',
  completed: 'Hoàn tất',
  cancelled: 'Đã hủy',
  returning_to_seller: 'Đang chuyển hoàn',
  returned_to_seller: 'Đã chuyển hoàn',
};

const PAYMENT_LABEL: Record<string, string> = {
  cod: 'Thanh toán khi nhận hàng',
  ewallet: 'Ví điện tử',
  card: 'Thẻ tín dụng / ghi nợ',
  bank_transfer: 'Chuyển khoản ngân hàng',
};

export const ORDER_CODE_PATTERN = /\bSL-[A-Z0-9]+\b/gi;

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

export function paymentLabel(method?: string): string {
  if (!method) return 'Chưa có thông tin';
  return PAYMENT_LABEL[method] ?? method;
}

export function formatVnd(amount: number): string {
  return `${amount.toLocaleString('vi-VN')} ₫`;
}

export function formatDate(iso?: string | null, withYear = true): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  return withYear ? `${day}/${month}/${d.getFullYear()}` : `${day}/${month}`;
}

export function formatTime(iso?: string): string {
  const d = iso ? new Date(iso) : new Date();
  return d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', hour12: false });
}

/** Order codes mentioned in a text, upper-cased, first occurrence order. */
export function orderCodesIn(text: string): string[] {
  const found = text.match(ORDER_CODE_PATTERN) ?? [];
  return [...new Set(found.map((c) => c.toUpperCase()))];
}

export interface TimelineStep {
  label: string;
  /** dd/mm when the order carries that moment, else empty (never invented). */
  date: string;
  reached: boolean;
  final: boolean;
}

// How far along the fulfilment path each status is (index into STEPS), or null when the path was left.
const STATUS_PROGRESS: Record<string, number | null> = {
  pending_payment: 0,
  confirmed: 0,
  packing: 1,
  shipped: 2,
  out_for_delivery: 2,
  delivery_failed: 2,
  delivered: 3,
  completed: 3,
  cancelled: null,
  returning_to_seller: null,
  returned_to_seller: null,
};

const STEP_LABELS = ['Đã đặt hàng', 'Đang chuẩn bị', 'Đang giao', 'Đã giao'];

export function timelineFor(order: Pick<OrderDetail, 'status' | 'placed_at' | 'delivered_at'>): TimelineStep[] | null {
  const progress = STATUS_PROGRESS[order.status];
  if (progress === null || progress === undefined) return null;
  const dates = [formatDate(order.placed_at, false), '', '', formatDate(order.delivered_at, false)];
  return STEP_LABELS.map((label, i) => ({
    label,
    date: dates[i],
    reached: i <= progress,
    final: i === STEP_LABELS.length - 1,
  }));
}

export function canRequestReturn(order: Pick<OrderDetail, 'available_actions'>): boolean {
  return (order.available_actions ?? []).some((a) => a.action === 'return');
}
