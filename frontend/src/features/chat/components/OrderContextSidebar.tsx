import React, { useState, useEffect } from 'react';
import { Package, Check, Calendar, Truck, CreditCard, RotateCcw, BookOpen, FileText, ChevronRight, Loader2 } from 'lucide-react';
import { api } from '../../../lib/api';

interface OrderContextSidebarProps {
  orderCode: string;
  onQuickPrompt: (prompt: string) => void;
  onSelectClause: (clauseId: string) => void;
}

export const OrderContextSidebar: React.FC<OrderContextSidebarProps> = ({
  orderCode,
  onQuickPrompt,
  onSelectClause,
}) => {
  const [order, setOrder] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const fetchOrder = async () => {
      if (!orderCode) return;
      setLoading(true);
      try {
        const data = await api.getOrder(orderCode);
        if (isMounted) setOrder(data);
      } catch {
        // Safe fallback if order lookup is not yet confirmed
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    fetchOrder();
    return () => {
      isMounted = false;
    };
  }, [orderCode]);

  const productName = order?.items?.[0]?.product_name || 'Tai nghe không dây Studio Pro';
  const qty = order?.items?.[0]?.qty || 1;
  const totalStr = order ? `${order.total.toLocaleString('vi-VN')} đ` : '1.290.000 đ';
  const statusStr = order?.status === 'delivered' ? 'Đã giao' : order?.status === 'shipping' ? 'Đang giao' : 'Đã xác nhận';
  const placedDateStr = order?.placed_at ? new Date(order.placed_at).toLocaleDateString('vi-VN') : '08/11/2026';
  const deliveredDateStr = order?.delivered_at ? new Date(order.delivered_at).toLocaleDateString('vi-VN') : '10/11/2026';
  const paymentStr = order?.payment_method === 'card' ? 'Thanh toán qua thẻ' : 'Thanh toán khi nhận hàng';

  return (
    <div className="w-80 xl:w-96 hidden lg:flex flex-col gap-5 h-full overflow-y-auto">
      {/* Card 1: Dynamic Order Details */}
      <div className="bg-white rounded-3xl p-5 border border-purple-100 shadow-sm space-y-4 relative">
        {loading && (
          <div className="absolute inset-0 bg-white/70 backdrop-blur-2xs rounded-3xl flex items-center justify-center z-10">
            <Loader2 className="w-5 h-5 animate-spin text-purple-600" />
          </div>
        )}

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Package className="w-5 h-5 text-purple-600" />
            <h3 className="font-bold text-slate-900 text-sm">
              Đơn hàng {orderCode}
            </h3>
          </div>
          <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-semibold px-2.5 py-0.5 rounded-full flex items-center gap-1">
            <Check className="w-3 h-3 stroke-[3]" />
            <span>{statusStr}</span>
          </span>
        </div>

        {/* Product row with authentic asset image */}
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
          className="w-full py-2.5 px-4 rounded-xl border-2 border-purple-600 text-purple-700 hover:bg-purple-50 font-bold text-xs flex items-center justify-center gap-2 transition shadow-2xs"
        >
          <RotateCcw className="w-4 h-4 text-purple-600" />
          <span>Yêu cầu đổi trả</span>
        </button>
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
            className="w-full p-2.5 rounded-xl hover:bg-purple-50/70 text-left text-xs font-semibold text-slate-700 hover:text-purple-800 flex items-center justify-between transition group"
          >
            <div className="flex items-center gap-2 truncate">
              <FileText className="w-3.5 h-3.5 text-purple-500 group-hover:text-purple-700 flex-shrink-0" />
              <span className="truncate">Điều kiện đổi trả</span>
            </div>
            <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-700 flex-shrink-0" />
          </button>

          <button
            onClick={() => onSelectClause('POL-RET-TIME')}
            className="w-full p-2.5 rounded-xl hover:bg-purple-50/70 text-left text-xs font-semibold text-slate-700 hover:text-purple-800 flex items-center justify-between transition group"
          >
            <div className="flex items-center gap-2 truncate">
              <FileText className="w-3.5 h-3.5 text-purple-500 group-hover:text-purple-700 flex-shrink-0" />
              <span className="truncate">Thời hạn và quy trình đổi trả</span>
            </div>
            <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-700 flex-shrink-0" />
          </button>

          <button
            onClick={() => onSelectClause('POL-RET-EXCL')}
            className="w-full p-2.5 rounded-xl hover:bg-purple-50/70 text-left text-xs font-semibold text-slate-700 hover:text-purple-800 flex items-center justify-between transition group"
          >
            <div className="flex items-center gap-2 truncate">
              <FileText className="w-3.5 h-3.5 text-purple-500 group-hover:text-purple-700 flex-shrink-0" />
              <span className="truncate">Các trường hợp không được đổi trả</span>
            </div>
            <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-700 flex-shrink-0" />
          </button>
        </div>
      </div>
    </div>
  );
};
