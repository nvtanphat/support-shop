import React from 'react';
import { Zap, Package, FileText, HelpCircle } from 'lucide-react';

interface HeroBannerProps {
  onQuickPrompt: (prompt: string) => void;
  onOpenOtpModal: () => void;
  onEscalate: () => void;
}

export const HeroBanner: React.FC<HeroBannerProps> = ({
  onQuickPrompt,
  onOpenOtpModal,
  onEscalate,
}) => {
  return (
    <div className="bg-gradient-to-r from-[#DACAFB] via-[#E5D9FC] to-[#F4EEFE] px-10 pt-3 pb-3.5 relative overflow-hidden flex-shrink-0">
      {/* 3D Robot Mascot Image from provided assets */}
      <div className="absolute right-10 top-1/2 -translate-y-1/2 hidden sm:flex items-center justify-center w-56 h-56 pointer-events-none select-none">
        <div className="absolute w-40 h-40 rounded-full bg-purple-300/40 blur-2xl"></div>
        <img
          src="/images/mascot/robot-support.png"
          alt="ShopSupport AI Robot"
          className="w-52 h-52 object-contain relative z-10 drop-shadow-xl transition-transform hover:scale-105"
        />
      </div>

      <div className="max-w-3xl relative z-10 space-y-2">
        <h1 className="text-[34px] leading-tight font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
          <span>Xin chào!</span>
          <span className="text-3xl">👋</span>
        </h1>
        <p className="text-[15px] text-slate-800 leading-snug font-normal max-w-xl">
          Tôi là trợ lý AI của ShopSupport, sẵn sàng hỗ trợ bạn 24/7 về đơn hàng, chính sách, đổi trả và các vấn đề khác.
        </p>

        {/* 4 Quick prompt chips */}
        <div className="flex flex-wrap gap-3 pt-2">
          <button
            onClick={onOpenOtpModal}
            className="px-5 py-2.5 bg-white hover:bg-[#FBF8FF] text-slate-900 hover:text-purple-700 rounded-full text-[15px] font-semibold flex items-center gap-2.5 shadow-pill transition hover:-translate-y-px"
          >
            <Zap className="w-5 h-5 text-purple-700" />
            <span>Tra cứu đơn hàng</span>
          </button>

          <button
            onClick={() => onQuickPrompt('Mình muốn đổi trả đơn hàng SL-8F3D9K vì tai nghe bị rè một bên.')}
            className="px-5 py-2.5 bg-white hover:bg-[#FBF8FF] text-slate-900 hover:text-purple-700 rounded-full text-[15px] font-semibold flex items-center gap-2.5 shadow-pill transition hover:-translate-y-px"
          >
            <Package className="w-5 h-5 text-purple-700" />
            <span>Đổi trả / Hoàn tiền</span>
          </button>

          <button
            onClick={() => onQuickPrompt('Chính sách đổi trả hàng tại shop quy định như thế nào?')}
            className="px-5 py-2.5 bg-white hover:bg-[#FBF8FF] text-slate-900 hover:text-purple-700 rounded-full text-[15px] font-semibold flex items-center gap-2.5 shadow-pill transition hover:-translate-y-px"
          >
            <FileText className="w-5 h-5 text-purple-700" />
            <span>Hỏi về chính sách</span>
          </button>

          <button
            onClick={onEscalate}
            className="px-5 py-2.5 bg-white hover:bg-[#FBF8FF] text-slate-900 hover:text-purple-700 rounded-full text-[15px] font-semibold flex items-center gap-2.5 shadow-pill transition hover:-translate-y-px"
          >
            <HelpCircle className="w-5 h-5 text-purple-700" />
            <span>Hỗ trợ khác</span>
          </button>
        </div>
      </div>
    </div>
  );
};
