import React, { useEffect, useState } from 'react';
import { X, BookOpen, Calendar } from 'lucide-react';
import { api } from '../lib/api';
import type { PolicyDetail } from '../lib/types';
import { formatDate } from '../lib/orderView';
import { useEscapeKey } from '../lib/useEscapeKey';

interface CitationModalProps {
  clauseId: string | null;
  onClose: () => void;
}

type Load = { status: 'loading' } | { status: 'ready'; policy: PolicyDetail } | { status: 'error'; message: string };

/** The clause the assistant cited, read from the policy index (never a placeholder text). */
export const CitationModal: React.FC<CitationModalProps> = ({ clauseId, onClose }) => {
  useEscapeKey(onClose);
  const [load, setLoad] = useState<Load>({ status: 'loading' });

  useEffect(() => {
    if (!clauseId) return;
    let cancelled = false;
    setLoad({ status: 'loading' });
    api
      .getPolicy(clauseId)
      .then((policy) => !cancelled && setLoad({ status: 'ready', policy }))
      .catch((err: unknown) =>
        !cancelled && setLoad({ status: 'error', message: err instanceof Error ? err.message : 'Không tải được điều khoản.' })
      );
    return () => {
      cancelled = true;
    };
  }, [clauseId]);

  if (!clauseId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        className="bg-white rounded-3xl shadow-2xl max-w-lg w-full p-6 text-slate-800 relative border border-brand-100"
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

        <div className="flex items-center gap-2.5 text-brand-700 font-bold mb-2">
          <BookOpen className="w-5 h-5" />
          <span id="modal-title" className="text-sm tracking-wide font-mono bg-brand-100 px-2 py-0.5 rounded-lg">
            {clauseId}
          </span>
        </div>

        <h3 className="text-base font-bold text-slate-900 mb-2">Điều khoản chính sách ShopLab</h3>

        {load.status === 'loading' && <p className="text-sm text-slate-500" role="status">Đang tải điều khoản...</p>}
        {load.status === 'error' && <p className="text-sm text-red-700" role="alert">{load.message}</p>}
        {load.status === 'ready' && (
          <div className="p-4 bg-brand-50/50 border border-brand-100 rounded-2xl text-sm text-slate-700 leading-relaxed mb-4">
            <p className="font-semibold text-slate-900 mb-1">{load.policy.title}</p>
            <p className="whitespace-pre-wrap">{load.policy.text}</p>
            <div className="text-xs text-slate-500 flex items-center gap-1 mt-3 pt-3 border-t border-brand-100">
              <Calendar className="w-3.5 h-3.5 text-brand-500" />
              Phiên bản {load.policy.version}, hiệu lực từ {formatDate(load.policy.effective_from)}
              {load.policy.effective_to ? ` đến ${formatDate(load.policy.effective_to)}` : ''}
            </div>
          </div>
        )}

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2.5 bg-brand-700 hover:bg-brand-800 text-white rounded-xl text-xs font-semibold shadow-md shadow-brand-200 transition"
          >
            Đã hiểu
          </button>
        </div>
      </div>
    </div>
  );
};
