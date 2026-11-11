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
    <div className="bg-gradient-to-r from-purple-100/90 via-purple-50/80 to-white rounded-3xl p-6 border border-purple-200/60 relative overflow-hidden shadow-xs">
      {/* 3D Robot Mascot Image from provided assets */}
      <div className="absolute right-4 top-1/2 -translate-y-1/2 hidden sm:flex items-center justify-center w-36 h-36 pointer-events-none select-none">
        <div className="absolute w-28 h-28 rounded-full bg-purple-300/30 blur-xl"></div>
        <img
          src="/images/mascot/robot-support.png"
          alt="ShopSupport AI Robot"
          className="w-32 h-32 object-contain relative z-10 drop-shadow-md transition-transform hover:scale-105"
        />
      </div>

      <div className="max-w-lg relative z-10 space-y-3">
        <h1 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2">
          <span>Xin chào!</span>
          <span className="text-2xl">👋</span>
        </h1>
        <p className="text-xs md:text-sm text-slate-600 leading-relaxed font-normal">
          Tôi là trợ lý AI của ShopSupport, sẵn sàng hỗ trợ bạn 24/7 về đơn hàng, chính sách, đổi trả và các vấn đề khác.
        </p>

        {/* 4 Quick prompt chips */}
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            onClick={onOpenOtpModal}
            className="px-3.5 py-2 bg-white/95 hover:bg-white text-slate-700 hover:text-purple-700 rounded-2xl text-xs font-semibold flex items-center gap-1.5 border border-purple-200/80 shadow-xs transition hover:shadow-sm"
          >
            <Zap className="w-3.5 h-3.5 text-purple-600" />
            <span>Tra cứu đơn hàng</span>
          </button>

          <button
            onClick={() => onQuickPrompt('Mình muốn đổi trả đơn hàng SL-8F3D9K vì tai nghe bị rè một bên.')}
            className="px-3.5 py-2 bg-white/95 hover:bg-white text-slate-700 hover:text-purple-700 rounded-2xl text-xs font-semibold flex items-center gap-1.5 border border-purple-200/80 shadow-xs transition hover:shadow-sm"
          >
            <Package className="w-3.5 h-3.5 text-purple-600" />
            <span>Đổi trả / Hoàn tiền</span>
          </button>

          <button
            onClick={() => onQuickPrompt('Chính sách đổi trả hàng tại shop quy định như thế nào?')}
            className="px-3.5 py-2 bg-white/95 hover:bg-white text-slate-700 hover:text-purple-700 rounded-2xl text-xs font-semibold flex items-center gap-1.5 border border-purple-200/80 shadow-xs transition hover:shadow-sm"
          >
            <FileText className="w-3.5 h-3.5 text-purple-600" />
            <span>Hỏi về chính sách</span>
          </button>

          <button
            onClick={onEscalate}
            className="px-3.5 py-2 bg-white/95 hover:bg-white text-slate-700 hover:text-purple-700 rounded-2xl text-xs font-semibold flex items-center gap-1.5 border border-purple-200/80 shadow-xs transition hover:shadow-sm"
          >
            <HelpCircle className="w-3.5 h-3.5 text-purple-600" />
            <span>Hỗ trợ khác</span>
          </button>
        </div>
      </div>
    </div>
  );
};
