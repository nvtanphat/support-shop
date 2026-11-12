import React, { useState, useEffect } from 'react';
import {
  Package,
  Check,
  Calendar,
  Truck,
  CreditCard,
  RotateCcw,
  BookOpen,
  FileText,
  ChevronRight,
  Loader2,
  ShieldAlert,
  KeyRound,
} from 'lucide-react';
import { api } from '../../../lib/api';

interface OrderContextSidebarProps {
  orderCode: string;
  onQuickPrompt: (prompt: string) => void;
  onSelectClause: (clauseId: string) => void;
  onOpenOtp?: () => void;
}

const RELATED_POLICIES = [
  { clauseId: 'POL-RET-ELIG', label: 'Điều kiện đổi trả' },
  { clauseId: 'POL-REF-METH', label: 'Thời gian hoàn tiền' },
  { clauseId: 'POL-CAN-PACK', label: 'Quy định hủy đơn' },
] as const;

export const OrderContextSidebar: React.FC<OrderContextSidebarProps> = ({
  orderCode,
  onQuickPrompt,
  onSelectClause,
  onOpenOtp,
}) => {
  const [order, setOrder] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const fetchOrder = async () => {
      if (!orderCode) {
        if (isMounted) {
          setOrder(null);
          setError(null);
        }
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await api.getOrder(orderCode);
        if (isMounted) {
          setOrder(data);
          setError(null);
        }
      } catch (err: any) {
        if (isMounted) {
          setOrder(null);
          setError(err?.message || 'Chưa được cấp quyền xem đơn hàng này');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    fetchOrder();
    return () => {
      isMounted = false;
    };
  }, [orderCode]);

  const firstItem = order?.items?.[0];
  const productName = firstItem?.product_name || 'Sản phẩm theo đơn';
  const qty = firstItem?.qty || 1;
  const totalStr = order ? `${Number(order.total).toLocaleString('vi-VN')} đ` : '';
  const statusStr =
    order?.status === 'delivered'
      ? 'Đã giao'
      : order?.status === 'shipping'
      ? 'Đang giao'
      : order?.status === 'confirmed'
      ? 'Đã xác nhận'
      : order?.status === 'cancelled'
      ? 'Đã hủy'
      : order?.status || '';
  const placedDateStr = order?.placed_at ? new Date(order.placed_at).toLocaleDateString('vi-VN') : '—';
  const deliveredDateStr = order?.delivered_at ? new Date(order.delivered_at).toLocaleDateString('vi-VN') : '—';
  const paymentStr =
    order?.payment_method === 'card'
      ? 'Thanh toán qua thẻ'
      : order?.payment_method === 'cod'
      ? 'Thanh toán khi nhận hàng'
      : order?.payment_method || '—';

  return (
    <div className="w-80 xl:w-[420px] hidden lg:flex flex-col gap-5 h-full overflow-y-auto">
      {/* Card 1: Dynamic Order Details */}
      <div className="bg-white/95 rounded-[28px] p-6 border border-[#ECE6FA] shadow-card space-y-4 relative">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Package className="w-5 h-5 text-purple-700" />
            <h3 className="font-bold text-slate-900 text-lg">
              Đơn hàng {orderCode}
            </h3>
          </div>
          {order && (
            <span className="bg-[#DDF6E5] text-[#15803D] text-sm font-bold px-3.5 py-1 rounded-full flex items-center gap-1.5">
              <Check className="w-4 h-4 stroke-[3]" />
              <span>{statusStr}</span>
            </span>
          )}
        </div>

        {loading ? (
          <div className="py-8 flex flex-col items-center justify-center gap-2 text-slate-400">
            <Loader2 className="w-6 h-6 animate-spin text-purple-700" />
            <span className="text-xs">Đang tải thông tin đơn hàng...</span>
          </div>
        ) : order ? (
          <>
            {/* Real Product Row */}
            <div className="flex items-center gap-3 pt-1 pb-4 border-b border-[#EEE8FB]">
              <div className="w-16 h-16 rounded-2xl bg-white border border-[#ECE6FA] flex items-center justify-center p-1.5 flex-shrink-0 overflow-hidden">
                <img
                  src="/images/products/wireless-headphones.png"
                  alt={productName}
                  className="w-full h-full object-contain"
                />
              </div>
              <div className="flex-1 min-w-0">
                <h4 className="font-bold text-slate-900 text-sm leading-snug line-clamp-2" title={productName}>
                  {productName}
                </h4>
              </div>
              <span className="text-sm text-slate-900">x{qty}</span>
              <span className="text-sm font-bold text-slate-900 whitespace-nowrap">{totalStr}</span>
            </div>

            {/* Meta rows from real backend data */}
            <div className="text-sm divide-y divide-[#EEE8FB]">
              <div className="flex items-center justify-between text-slate-600 py-3">
                <span className="flex items-center gap-2 text-slate-700">
                  <Calendar className="w-5 h-5" />
                  <span>Ngày đặt hàng</span>
                </span>
                <span className="font-medium text-slate-900">{placedDateStr}</span>
              </div>

              <div className="flex items-center justify-between text-slate-600 py-3">
                <span className="flex items-center gap-2 text-slate-700">
                  <Truck className="w-5 h-5" />
                  <span>Ngày giao hàng</span>
                </span>
                <span className="font-medium text-slate-900">{deliveredDateStr}</span>
              </div>

              <div className="flex items-center justify-between text-slate-600 py-3">
                <span className="flex items-center gap-2 text-slate-700">
                  <CreditCard className="w-5 h-5" />
                  <span className="whitespace-nowrap">Phương thức thanh toán</span>
                </span>
                <span className="font-medium text-slate-900 text-right" title={paymentStr}>
                  {paymentStr}
                </span>
              </div>
            </div>

            {/* Action button */}
            <button
              onClick={() => onQuickPrompt(`Tạo yêu cầu đổi trả cho đơn hàng ${orderCode}`)}
              className="w-full py-3.5 px-4 rounded-2xl border-[1.5px] border-purple-700 text-purple-700 hover:bg-purple-50 font-bold text-base flex items-center justify-center gap-2.5 transition cursor-pointer"
            >
              <RotateCcw className="w-5 h-5 text-purple-700" />
              <span>Yêu cầu đổi trả</span>
            </button>
          </>
        ) : (
          /* Unauthorized or Unverified State */
          <div className="bg-[#F6F1FF] border border-[#E4D9FB] rounded-2xl p-4 space-y-3">
            <div className="flex items-center gap-2 text-purple-900">
              <ShieldAlert className="w-4 h-4 text-purple-700 flex-shrink-0" />
              <h4 className="font-bold text-sm">Chi tiết đơn hàng được bảo mật</h4>
            </div>
            <p className="text-xs text-slate-700 leading-relaxed">
              {error ? `${error}. ` : ''}Để bảo vệ thông tin đơn hàng <strong>{orderCode}</strong>, quý khách vui lòng xác thực OTP qua số điện thoại mua hàng để xem thông tin chi tiết.
            </p>
            {onOpenOtp ? (
              <button
                onClick={onOpenOtp}
                className="w-full py-2.5 px-3 bg-gradient-to-br from-[#6D28D9] to-[#4C1D95] hover:from-[#5B21B6] hover:to-[#3B0F8C] text-white rounded-2xl font-bold text-sm transition flex items-center justify-center gap-1.5 shadow-chip cursor-pointer"
              >
                <KeyRound className="w-5 h-5" />
                <span>Xác thực OTP tra cứu</span>
              </button>
            ) : (
              <button
                onClick={() => onQuickPrompt(`Tôi muốn xác thực OTP cho đơn hàng ${orderCode}`)}
                className="w-full py-2.5 px-3 bg-gradient-to-br from-[#6D28D9] to-[#4C1D95] hover:from-[#5B21B6] hover:to-[#3B0F8C] text-white rounded-2xl font-bold text-sm transition flex items-center justify-center gap-1.5 shadow-chip cursor-pointer"
              >
                <KeyRound className="w-5 h-5" />
                <span>Yêu cầu gửi OTP</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* Card 2: Related Policies */}
      <div className="bg-white/95 rounded-[28px] p-6 border border-[#ECE6FA] shadow-card space-y-3">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-purple-700" />
          <h3 className="font-bold text-slate-900 text-lg">
            Chính sách liên quan
          </h3>
        </div>

        <div className="divide-y divide-[#EEE8FB]">
          {RELATED_POLICIES.map((policy) => (
            <button
              key={policy.clauseId}
              onClick={() => onSelectClause(policy.clauseId)}
              className="w-full text-left py-3 hover:bg-[#F7F3FF] transition flex items-center justify-between group cursor-pointer"
            >
              <span className="flex items-center gap-3">
                <span className="w-10 h-10 rounded-xl bg-[#F4F0FC] flex items-center justify-center flex-shrink-0">
                  <FileText className="w-5 h-5 text-slate-900" />
                </span>
                <span className="font-medium text-slate-900 text-base">{policy.label}</span>
              </span>
              <ChevronRight className="w-5 h-5 text-slate-900 group-hover:translate-x-0.5 transition" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
