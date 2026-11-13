import React from 'react';
import { X, BookOpen, ChevronRight } from 'lucide-react';
import type { PolicySummary } from '../lib/types';

interface PolicyListModalProps {
  open: boolean;
  policies: PolicySummary[];
  loading: boolean;
  error?: string;
  onSelect: (clauseId: string) => void;
  onClose: () => void;
}

/** Every clause currently in force, opened from the "Chính sách" tab. */
export const PolicyListModal: React.FC<PolicyListModalProps> = ({ open, policies, loading, error, onSelect, onClose }) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        className="bg-white rounded-3xl shadow-2xl max-w-lg w-full p-6 text-slate-800 relative border border-purple-100 max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="policy-list-title"
      >
        <button onClick={onClose} className="absolute top-5 right-5 text-slate-400 hover:text-slate-600 rounded-xl p-1 hover:bg-slate-100" aria-label="Đóng">
          <X className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-2.5 text-purple-700 font-bold mb-4">
          <BookOpen className="w-5 h-5" />
          <h3 id="policy-list-title" className="text-base text-slate-900">Chính sách đang có hiệu lực</h3>
        </div>
        {loading && <p className="text-sm text-slate-500" role="status">Đang tải chính sách...</p>}
        {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
        {!loading && !error && policies.length === 0 && <p className="text-sm text-slate-500">Chưa có điều khoản nào đang có hiệu lực.</p>}
        <ul className="divide-y divide-purple-100">
          {policies.map((p) => (
            <li key={p.clause_id}>
              <button
                onClick={() => onSelect(p.clause_id)}
                className="w-full flex items-center justify-between gap-3 py-3 text-left hover:bg-purple-50 rounded-xl px-2"
              >
                <span>
                  <span className="block text-sm font-semibold text-slate-900">{p.title}</span>
                  <span className="block text-xs text-slate-500 font-mono">{p.clause_id}</span>
                </span>
                <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};
