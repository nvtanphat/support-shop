import React from 'react';
import { AlertTriangle } from 'lucide-react';

/** Simulation warning. Fixed to the bottom edge so it never changes the layout of the interface. */
export const EnvironmentBanner: React.FC = () => {
  return (
    <div
      role="banner"
      className="fixed bottom-1.5 left-1/2 -translate-x-1/2 z-20 bg-[#FFF4D6] text-amber-900 border border-amber-200 px-3 py-0.5 rounded-full text-[10px] font-semibold flex items-center gap-1.5 shadow-sm pointer-events-none"
    >
      <AlertTriangle className="w-3 h-3 text-amber-700 flex-shrink-0" />
      <span>Môi trường mô phỏng — Không có giao dịch thật</span>
    </div>
  );
};
