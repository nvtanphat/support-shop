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
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 text-slate-850 relative animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="modal-title"
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 rounded-lg p-1 transition"
          aria-label="Đóng"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2.5 text-emerald-700 font-semibold mb-3">
          <BookOpen className="w-5 h-5" />
          <span id="modal-title" className="text-base tracking-wide uppercase font-mono">
            {clauseId}
          </span>
        </div>

        <h3 className="text-lg font-bold text-slate-900 mb-2">
          Điều khoản chính sách ShopLab
        </h3>

        <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700 leading-relaxed mb-4">
          <p className="mb-2">
            Đây là điều khoản chính thức được tham chiếu trong câu trả lời của trợ lý AI.
          </p>
          <div className="text-xs text-slate-500 flex items-center gap-4 mt-3 pt-3 border-t border-slate-200">
            <span className="flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5" /> Hiệu lực: 01/11/2026
            </span>
            <span className="flex items-center gap-1 text-emerald-600">
              <ShieldCheck className="w-3.5 h-3.5" /> Đã xác thực nguồn
            </span>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium transition"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
};
