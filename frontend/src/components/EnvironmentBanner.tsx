import React from 'react';
import { AlertTriangle } from 'lucide-react';

export const EnvironmentBanner: React.FC = () => {
  return (
    <div
      role="banner"
      className="bg-amber-500 text-slate-950 px-4 py-1.5 text-xs font-semibold flex items-center justify-center gap-2 shadow-sm uppercase tracking-wider"
    >
      <AlertTriangle className="w-4 h-4 text-slate-950 flex-shrink-0" />
      <span>Môi trường mô phỏng — Không có giao dịch thật</span>
    </div>
  );
};
