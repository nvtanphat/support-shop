import React from 'react';
import { AlertTriangle } from 'lucide-react';

export const EnvironmentBanner: React.FC = () => {
  return (
    <div
      role="banner"
      className="bg-[#FFF4D6] text-amber-900 border-b border-amber-200 px-4 py-1.5 text-xs font-semibold flex items-center justify-center gap-2"
    >
      <AlertTriangle className="w-4 h-4 text-amber-700 flex-shrink-0" />
      <span>Môi trường mô phỏng — Không có giao dịch thật</span>
    </div>
  );
};
