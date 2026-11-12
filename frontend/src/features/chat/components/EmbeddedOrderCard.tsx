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
  const steps = [
    { label: 'Đã đặt hàng', date: '08/11' },
    { label: 'Đang chuẩn bị', date: '08/11' },
    { label: 'Đang giao', date: '09/11' },
    { label: 'Đã giao', date: '10/11' },
  ];

  return (
    <div className="mt-3 space-y-3">
      <div className="p-4 bg-white rounded-2xl border border-[#ECE6FA] shadow-card grid md:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] gap-6 items-center">
        {/* Product snippet */}
        <div className="flex items-center gap-4 min-w-0">
          <div className="w-[84px] h-[84px] rounded-2xl bg-white border border-[#ECE6FA] shadow-pill flex items-center justify-center p-2 flex-shrink-0 overflow-hidden">
            <img
              src="/images/products/wireless-headphones.png"
              alt="Tai nghe không dây Studio Pro"
              className="w-full h-full object-contain"
            />
          </div>
          <div className="min-w-0">
            <h4 className="font-bold text-slate-900 text-base">Tai nghe không dây Studio Pro</h4>
            <div className="flex flex-wrap items-center gap-x-3 text-sm text-slate-600 mt-1.5">
              <span>Mã đơn: <span className="text-purple-700">{orderCode}</span></span>
              <span className="h-4 w-px bg-[#DCD3F3]" aria-hidden="true" />
              <span>Ngày đặt: 08/11/2026</span>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 text-sm text-slate-600 mt-1">
              <span>Số lượng: x1</span>
              <span className="h-4 w-px bg-[#DCD3F3]" aria-hidden="true" />
              <span>Tổng tiền: <strong className="text-slate-900">1.290.000 đ</strong></span>
            </div>
          </div>
        </div>

        {/* Stepper timeline with connecting line */}
        <ol className="relative grid grid-cols-4 text-center text-sm" aria-label="Tiến trình đơn hàng">
          <span className="absolute top-3.5 left-[12.5%] right-[12.5%] h-[3px] bg-purple-700 rounded-full" aria-hidden="true" />
          {steps.map((step, i) => {
            const isLast = i === steps.length - 1;
            return (
              <li key={step.label} className="relative flex flex-col items-center">
                <span
                  className={`w-7 h-7 rounded-full flex items-center justify-center mb-2 ring-4 ring-white ${
                    isLast ? 'bg-[#16A34A] text-white' : 'bg-white border-[2.5px] border-purple-700 text-purple-700'
                  }`}
                >
                  <Check className="w-3.5 h-3.5 stroke-[3]" />
                </span>
                <span className={isLast ? 'font-bold text-[#15803D]' : 'font-semibold text-slate-800'}>{step.label}</span>
                <span className={isLast ? 'text-[#15803D] font-semibold' : 'text-slate-500'}>{step.date}</span>
              </li>
            );
          })}
        </ol>
      </div>

      {/* Eligibility Info Box */}
      <div className="px-5 py-3.5 bg-[#EFE9FC] rounded-2xl text-[15px] space-y-1.5 text-slate-900">
        <div className="flex items-center gap-2 font-bold text-slate-900">
          <Info className="w-5 h-5 text-purple-700 flex-shrink-0" />
          <span>Bạn có thể đổi trả sản phẩm này.</span>
        </div>
        <ul className="pl-7 space-y-1 list-disc text-slate-900">
          <li>Thời hạn đổi trả: trong 7 ngày kể từ ngày nhận hàng (đến hết 23:59 ngày 17/11/2026).</li>
          <li>Điều kiện: sản phẩm bị lỗi kỹ thuật, còn nguyên tem và phụ kiện.</li>
        </ul>
      </div>

      <p className="text-base text-slate-800">Bạn muốn mình tạo yêu cầu đổi trả cho đơn hàng này chứ?</p>

      {/* Quick Action Prompt Buttons */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={() => onQuickPrompt(`Tạo yêu cầu đổi trả đơn hàng ${orderCode}`)}
          className="px-5 py-3 bg-gradient-to-br from-[#6D28D9] to-[#4C1D95] hover:from-[#5B21B6] hover:to-[#3B0F8C] text-white rounded-2xl text-base font-semibold flex items-center gap-2.5 shadow-cta transition"
        >
          <RotateCcw className="w-5 h-5" />
          <span>Tạo yêu cầu đổi trả</span>
        </button>

        <button
          onClick={() => onSelectClause('POL-RET-ELIG')}
          className="px-5 py-3 bg-white hover:bg-[#FBF8FF] text-slate-900 rounded-2xl text-base font-semibold flex items-center gap-2.5 shadow-pill transition"
        >
          <FileText className="w-5 h-5 text-slate-900" />
          <span>Xem chi tiết chính sách</span>
        </button>
      </div>
    </div>
  );
};
