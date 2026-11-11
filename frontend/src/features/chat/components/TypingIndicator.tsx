import React from 'react';
import { Sparkles } from 'lucide-react';

interface TypingIndicatorProps {
  progressText?: string | null;
}

export const TypingIndicator: React.FC<TypingIndicatorProps> = ({ progressText }) => {
  return (
    <div className="flex gap-3 items-end justify-start animate-in fade-in duration-200">
      <div className="w-10 h-10 rounded-2xl overflow-hidden flex items-center justify-center flex-shrink-0 shadow-sm mb-1 bg-purple-50 border border-purple-100">
        <img
          src="/images/avatars/ai-assistant-avatar.png"
          alt="ShopSupport AI"
          className="w-full h-full object-cover animate-pulse"
          onError={(e) => {
            (e.target as HTMLElement).style.display = 'none';
          }}
        />
      </div>
      <div className="space-y-1">
        <div className="flex items-center gap-2 px-1 text-xs">
          <span className="font-bold text-slate-900">ShopSupport AI</span>
          <span className="bg-purple-600 text-white text-[10px] font-extrabold px-1.5 py-0.5 rounded-md flex items-center gap-1">
            <Sparkles className="w-2.5 h-2.5" />
            <span>AI</span>
          </span>
        </div>
        <div className="p-3.5 px-4 rounded-3xl bg-white border border-purple-200/80 rounded-bl-xs shadow-xs flex items-center gap-3">
          <div className="flex gap-1.5 items-center">
            <span className="w-2 h-2 rounded-full bg-purple-600 animate-bounce [animation-delay:-0.3s]" />
            <span className="w-2 h-2 rounded-full bg-purple-500 animate-bounce [animation-delay:-0.15s]" />
            <span className="w-2 h-2 rounded-full bg-purple-400 animate-bounce" />
          </div>
          <span className="text-xs text-purple-700 font-medium">
            {progressText || 'ShopSupport AI đang suy nghĩ...'}
          </span>
        </div>
      </div>
    </div>
  );
};
