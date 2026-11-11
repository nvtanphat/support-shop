import React from 'react';
import { Check, RotateCcw, FileText, Info } from 'lucide-react';

interface EmbeddedOrderCardProps {
  orderCode?: string;
  onQuickPrompt: (prompt: string) => void;
  onSelectClause: (clauseId: string) => void;
}

export const EmbeddedOrderCard: React.FC<EmbeddedOrderCardProps> = ({
  orderCode = 'SL-8F3D9K',
  onQuickPrompt,
  onSelectClause,
}) => {
  return (
    <div className="mt-3.5 p-4 bg-white rounded-2xl border border-purple-100 shadow-sm space-y-3.5">
      {/* Product snippet */}
      <div className="flex items-center gap-3.5">
        <div className="w-14 h-14 rounded-xl bg-purple-50 border border-purple-100 flex items-center justify-center p-1.5 flex-shrink-0 overflow-hidden">
          <img
            src="/images/products/wireless-headphones.png"
            alt="Tai nghe không dây Studio Pro"
            className="w-full h-full object-contain"
          />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="font-bold text-slate-900 text-sm truncate">
            Tai nghe không dây Studio Pro
          </h4>
          <div className="flex flex-wrap items-center gap-x-2 text-xs text-slate-500 mt-0.5">
            <span>Mã đơn: <strong className="font-mono text-purple-700">{orderCode}</strong></span>
            <span>•</span>
            <span>Ngày đặt: 08/11/2026</span>
            <span>•</span>
            <span>Số lượng: <strong className="text-slate-800">x1</strong></span>
            <span>•</span>
            <span>Tổng tiền: <strong className="text-slate-900">1.290.000 đ</strong></span>
          </div>
        </div>
      </div>

      {/* Stepper timeline */}
      <div className="pt-2 border-t border-slate-100">
        <div className="grid grid-cols-4 gap-2 text-center text-[11px]">
          <div className="flex flex-col items-center">
            <div className="w-6 h-6 rounded-full bg-purple-600 text-white flex items-center justify-center mb-1 shadow-2xs">
              <Check className="w-3.5 h-3.5 stroke-[3]" />
            </div>
            <span className="font-semibold text-slate-800">Đã đặt hàng</span>
            <span className="text-[10px] text-slate-400">08/11</span>
          </div>

          <div className="flex flex-col items-center">
            <div className="w-6 h-6 rounded-full bg-purple-600 text-white flex items-center justify-center mb-1 shadow-2xs">
              <Check className="w-3.5 h-3.5 stroke-[3]" />
            </div>
            <span className="font-semibold text-slate-800">Đang chuẩn bị</span>
            <span className="text-[10px] text-slate-400">08/11</span>
          </div>

          <div className="flex flex-col items-center">
            <div className="w-6 h-6 rounded-full bg-purple-600 text-white flex items-center justify-center mb-1 shadow-2xs">
              <Check className="w-3.5 h-3.5 stroke-[3]" />
            </div>
            <span className="font-semibold text-slate-800">Đang giao</span>
            <span className="text-[10px] text-slate-400">09/11</span>
          </div>

          <div className="flex flex-col items-center">
            <div className="w-6 h-6 rounded-full bg-emerald-500 text-white flex items-center justify-center mb-1 shadow-xs">
              <Check className="w-3.5 h-3.5 stroke-[3]" />
            </div>
            <span className="font-bold text-emerald-700">Đã giao</span>
            <span className="text-[10px] text-emerald-600 font-medium">10/11</span>
          </div>
        </div>
      </div>

      {/* Eligibility Info Box */}
      <div className="p-3 bg-purple-50/80 border border-purple-100 rounded-xl text-xs space-y-1 text-slate-700">
        <div className="flex items-center gap-1.5 font-bold text-purple-900">
          <Info className="w-4 h-4 text-purple-600 flex-shrink-0" />
          <span>Bạn có thể đổi trả sản phẩm này.</span>
        </div>
        <ul className="pl-5 space-y-0.5 list-disc text-slate-600 text-[11px]">
          <li>Thời hạn đổi trả: trong 7 ngày kể từ ngày nhận hàng (đến hết 23:59 ngày 17/11/2026).</li>
          <li>Điều kiện: sản phẩm bị lỗi kỹ thuật, còn nguyên tem và phụ kiện.</li>
        </ul>
      </div>

      {/* Quick Action Prompt Buttons */}
      <div className="pt-1 flex flex-wrap gap-2">
        <button
          onClick={() => onQuickPrompt(`Tạo yêu cầu đổi trả đơn hàng ${orderCode}`)}
          className="px-3.5 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-purple-200 transition"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Tạo yêu cầu đổi trả</span>
        </button>

        <button
          onClick={() => onSelectClause('POL-RET-ELIG')}
          className="px-3.5 py-2 bg-white hover:bg-purple-50 text-purple-700 border border-purple-200 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition"
        >
          <FileText className="w-3.5 h-3.5 text-purple-600" />
          <span>Xem chi tiết chính sách</span>
        </button>
      </div>
    </div>
  );
};
