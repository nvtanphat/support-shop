import React from 'react';
import { X, BookOpen, Calendar, ShieldCheck } from 'lucide-react';

interface CitationModalProps {
  clauseId: string | null;
  onClose: () => void;
}

export const CitationModal: React.FC<CitationModalProps> = ({ clauseId, onClose }) => {
  if (!clauseId) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-3xl shadow-2xl max-w-lg w-full p-6 text-slate-800 relative border border-purple-100 animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="modal-title"
      >
        <button
          onClick={onClose}
          className="absolute top-5 right-5 text-slate-400 hover:text-slate-600 rounded-xl p-1 hover:bg-slate-100 transition"
          aria-label="Đóng"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2.5 text-purple-700 font-bold mb-2">
          <BookOpen className="w-5 h-5" />
          <span id="modal-title" className="text-sm tracking-wide uppercase font-mono bg-purple-100 px-2 py-0.5 rounded-lg">
            {clauseId}
          </span>
        </div>

        <h3 className="text-base font-bold text-slate-900 mb-2">
          Điều khoản chính sách ShopLab (ShopSupport AI 2026)
        </h3>

        <div className="p-4 bg-purple-50/50 border border-purple-100 rounded-2xl text-xs text-slate-700 leading-relaxed mb-4">
          <p className="mb-2">
            Điều khoản chính thức được đối chiếu và tham chiếu trực tiếp từ nguồn văn bản pháp lý TMĐT của cửa hàng.
          </p>
          <div className="text-[11px] text-slate-500 flex items-center gap-4 mt-3 pt-3 border-t border-purple-100">
            <span className="flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5 text-purple-500" /> Phiên bản: 01/11/2026
            </span>
            <span className="flex items-center gap-1 text-purple-700 font-semibold">
              <ShieldCheck className="w-3.5 h-3.5 text-purple-600" /> Bất biến S4/S5 xác thực
            </span>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2.5 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-xs font-semibold shadow-md shadow-purple-200 transition"
          >
            Đã hiểu
          </button>
        </div>
      </div>
    </div>
  );
};
