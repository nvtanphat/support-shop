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
    <div className="w-80 xl:w-96 hidden lg:flex flex-col gap-5 h-full overflow-y-auto">
      {/* Card 1: Dynamic Order Details */}
      <div className="bg-white rounded-3xl p-5 border border-purple-100 shadow-sm space-y-4 relative">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Package className="w-5 h-5 text-purple-600" />
            <h3 className="font-bold text-slate-900 text-sm">
              Đơn hàng {orderCode}
            </h3>
          </div>
          {order && (
            <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-semibold px-2.5 py-0.5 rounded-full flex items-center gap-1">
              <Check className="w-3 h-3 stroke-[3]" />
              <span>{statusStr}</span>
            </span>
          )}
        </div>

        {loading ? (
          <div className="py-8 flex flex-col items-center justify-center gap-2 text-slate-400">
            <Loader2 className="w-6 h-6 animate-spin text-purple-600" />
            <span className="text-xs">Đang tải thông tin đơn hàng...</span>
          </div>
        ) : order ? (
          <>
            {/* Real Product Row */}
            <div className="flex items-center gap-3 pt-1">
              <div className="w-14 h-14 rounded-2xl bg-purple-50 border border-purple-100 flex items-center justify-center p-1.5 flex-shrink-0 overflow-hidden">
                <img
                  src="/images/products/wireless-headphones.png"
                  alt={productName}
                  className="w-full h-full object-contain"
                />
              </div>
              <div className="flex-1 min-w-0">
                <h4 className="font-bold text-slate-900 text-xs truncate" title={productName}>
                  {productName}
                </h4>
                <div className="flex items-center justify-between text-xs text-slate-500 mt-1">
                  <span>x{qty}</span>
                  <span className="font-bold text-slate-900">{totalStr}</span>
                </div>
              </div>
            </div>

            {/* Meta rows from real backend data */}
            <div className="space-y-2 text-xs pt-2 border-t border-slate-100">
              <div className="flex items-center justify-between text-slate-600">
                <span className="flex items-center gap-1.5 text-slate-400">
                  <Calendar className="w-3.5 h-3.5" />
                  <span>Ngày đặt hàng</span>
                </span>
                <span className="font-semibold text-slate-800">{placedDateStr}</span>
              </div>

              <div className="flex items-center justify-between text-slate-600">
                <span className="flex items-center gap-1.5 text-slate-400">
                  <Truck className="w-3.5 h-3.5" />
                  <span>Ngày giao hàng</span>
                </span>
                <span className="font-semibold text-slate-800">{deliveredDateStr}</span>
              </div>

              <div className="flex items-center justify-between text-slate-600">
                <span className="flex items-center gap-1.5 text-slate-400">
                  <CreditCard className="w-3.5 h-3.5" />
                  <span>Phương thức thanh toán</span>
                </span>
                <span className="font-medium text-slate-800 truncate max-w-[140px] text-right" title={paymentStr}>
                  {paymentStr}
                </span>
              </div>
            </div>

            {/* Action button */}
            <button
              onClick={() => onQuickPrompt(`Tạo yêu cầu đổi trả cho đơn hàng ${orderCode}`)}
              className="w-full py-2.5 px-4 rounded-xl border-2 border-purple-600 text-purple-700 hover:bg-purple-50 font-bold text-xs flex items-center justify-center gap-2 transition shadow-2xs cursor-pointer"
            >
              <RotateCcw className="w-4 h-4 text-purple-600" />
              <span>Yêu cầu đổi trả</span>
            </button>
          </>
        ) : (
          /* Unauthorized or Unverified State */
          <div className="bg-amber-50/70 border border-amber-200 rounded-2xl p-4 space-y-3">
            <div className="flex items-center gap-2 text-amber-800">
              <ShieldAlert className="w-4 h-4 text-amber-600 flex-shrink-0" />
              <h4 className="font-bold text-xs">Chi tiết đơn hàng được bảo mật</h4>
            </div>
            <p className="text-xs text-amber-700 leading-relaxed">
              {error ? `${error}. ` : ''}Để bảo vệ thông tin đơn hàng <strong>{orderCode}</strong>, quý khách vui lòng xác thực OTP qua số điện thoại mua hàng để xem thông tin chi tiết.
            </p>
            {onOpenOtp ? (
              <button
                onClick={onOpenOtp}
                className="w-full py-2 px-3 bg-amber-600 hover:bg-amber-700 text-white rounded-xl font-bold text-xs transition flex items-center justify-center gap-1.5 shadow-2xs cursor-pointer"
              >
                <KeyRound className="w-3.5 h-3.5" />
                <span>Xác thực OTP tra cứu</span>
              </button>
            ) : (
              <button
                onClick={() => onQuickPrompt(`Tôi muốn xác thực OTP cho đơn hàng ${orderCode}`)}
                className="w-full py-2 px-3 bg-amber-600 hover:bg-amber-700 text-white rounded-xl font-bold text-xs transition flex items-center justify-center gap-1.5 shadow-2xs cursor-pointer"
              >
                <KeyRound className="w-3.5 h-3.5" />
                <span>Yêu cầu gửi OTP</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* Card 2: Related Policies */}
      <div className="bg-white rounded-3xl p-5 border border-purple-100 shadow-sm space-y-3">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-purple-600" />
          <h3 className="font-bold text-slate-900 text-sm">
            Chính sách liên quan
          </h3>
        </div>

        <div className="space-y-1.5 pt-1">
          <button
            onClick={() => onSelectClause('POL-RET-ELIG')}
            className="w-full text-left p-3 rounded-2xl hover:bg-purple-50/60 border border-transparent hover:border-purple-100 transition flex items-center justify-between group cursor-pointer"
          >
            <div className="flex items-center gap-2.5">
              <FileText className="w-4 h-4 text-slate-400 group-hover:text-purple-600 transition" />
              <div>
                <span className="font-semibold text-slate-800 group-hover:text-purple-900 text-xs block">
                  Điều kiện đổi trả 7 ngày
                </span>
                <span className="text-[11px] text-slate-400">Điều 3.1 &bull; Chính sách đổi trả</span>
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-purple-600 group-hover:translate-x-0.5 transition" />
          </button>

          <button
            onClick={() => onSelectClause('POL-REF-METH')}
            className="w-full text-left p-3 rounded-2xl hover:bg-purple-50/60 border border-transparent hover:border-purple-100 transition flex items-center justify-between group cursor-pointer"
          >
            <div className="flex items-center gap-2.5">
              <FileText className="w-4 h-4 text-slate-400 group-hover:text-purple-600 transition" />
              <div>
                <span className="font-semibold text-slate-800 group-hover:text-purple-900 text-xs block">
                  Thời gian hoàn tiền
                </span>
                <span className="text-[11px] text-slate-400">Điều 4.2 &bull; Quy trình hoàn tiền</span>
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-purple-600 group-hover:translate-x-0.5 transition" />
          </button>

          <button
            onClick={() => onSelectClause('POL-CAN-PACK')}
            className="w-full text-left p-3 rounded-2xl hover:bg-purple-50/60 border border-transparent hover:border-purple-100 transition flex items-center justify-between group cursor-pointer"
          >
            <div className="flex items-center gap-2.5">
              <FileText className="w-4 h-4 text-slate-400 group-hover:text-purple-600 transition" />
              <div>
                <span className="font-semibold text-slate-800 group-hover:text-purple-900 text-xs block">
                  Quy định hủy đơn
                </span>
                <span className="text-[11px] text-slate-400">Điều 2.1 &bull; Hủy đơn hàng</span>
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-purple-600 group-hover:translate-x-0.5 transition" />
          </button>
        </div>
      </div>
    </div>
  );
};
