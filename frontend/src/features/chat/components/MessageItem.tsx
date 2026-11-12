import React from 'react';
import { Message } from '../../../lib/types';
import { EmbeddedOrderCard } from './EmbeddedOrderCard';
import { User, Headphones, Sparkles, ShieldCheck } from 'lucide-react';

interface MessageItemProps {
  message: Message;
  onSelectClause: (clauseId: string) => void;
  onQuickPrompt: (prompt: string) => void;
}

export const MessageItem: React.FC<MessageItemProps> = ({
  message,
  onSelectClause,
  onQuickPrompt,
}) => {
  const isAsst = message.role === 'assistant';
  const isStaff = message.role === 'staff';
  const isCust = message.role === 'customer';

  // Render message content with clickable policy badges and order embed
  const renderContent = () => {
    if (!isAsst) {
      return <div className="whitespace-pre-wrap">{message.content}</div>;
    }

    const citationRegex = /\[(POL-[A-Z0-9-]+)\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = citationRegex.exec(message.content)) !== null) {
      const clauseId = match[1];
      if (match.index > lastIndex) {
        parts.push(message.content.substring(lastIndex, match.index));
      }
      parts.push(
        <button
          key={`${clauseId}-${match.index}`}
          onClick={() => onSelectClause(clauseId)}
          className="inline-flex items-center gap-1 mx-1 px-2 py-0.5 bg-purple-100 hover:bg-purple-200 text-purple-800 text-xs font-mono font-semibold rounded-md border border-purple-300 transition shadow-2xs"
          title="Bấm để xem nguyên văn điều khoản chính sách"
        >
          <ShieldCheck className="w-3 h-3 text-purple-700" />
          <span>[{clauseId}]</span>
        </button>
      );
      lastIndex = match.index + match[0].length;
    }

    if (lastIndex < message.content.length) {
      parts.push(message.content.substring(lastIndex));
    }

    const hasOrderEmbed = message.content.includes('SL-8F3D9K') || message.content.includes('8F3D9K');

    return (
      <div className="space-y-3">
        <div className="whitespace-pre-wrap leading-relaxed">{parts}</div>
        {hasOrderEmbed && (
          <EmbeddedOrderCard
            orderCode="SL-8F3D9K"
            onQuickPrompt={onQuickPrompt}
            onSelectClause={onSelectClause}
          />
        )}
      </div>
    );
  };

  const timeLabel = message.created_at
    ? new Date(message.created_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
    : '';

  return (
    <div className={`flex gap-3 items-start ${isCust ? 'justify-end' : 'justify-start'}`}>
      {!isCust && (
        <div className="w-12 h-12 rounded-full overflow-hidden flex items-center justify-center flex-shrink-0 bg-white shadow-pill">
          {isAsst ? (
            <img
              src="/images/avatars/ai-assistant-avatar.png"
              alt="ShopSupport AI"
              className="w-full h-full object-cover"
              onError={(e) => {
                // Fallback to bot icon if image fails
                (e.target as HTMLElement).style.display = 'none';
              }}
            />
          ) : (
            <div className="w-full h-full bg-gradient-to-tr from-purple-600 to-indigo-500 text-white flex items-center justify-center">
              <Headphones className="w-5 h-5" />
            </div>
          )}
        </div>
      )}

      <div className="max-w-[90%] md:max-w-[85%] space-y-1">
        {!isCust && (
          <div className="flex items-center gap-2 px-1 text-sm">
            <span className="font-bold text-slate-900 text-base">
              {isStaff ? 'Chuyên viên ShopSupport' : 'ShopSupport AI'}
            </span>
            {isAsst && (
              <span className="bg-purple-700 text-white text-xs font-bold px-2 py-0.5 rounded-md flex items-center gap-1">
                <Sparkles className="w-2.5 h-2.5" />
                <span>AI</span>
              </span>
            )}
            {timeLabel && <span className="ml-auto text-sm text-slate-600">{timeLabel}</span>}
          </div>
        )}

        <div
          className={`px-5 py-3 rounded-3xl text-[15px] leading-relaxed ${
            isCust
              ? 'bg-[#EEE8FC] text-slate-900 rounded-br-lg'
              : isStaff
              ? 'bg-indigo-50 text-indigo-950 border border-indigo-200 rounded-bl-xs shadow-xs'
              : 'bg-transparent text-slate-800 px-1 py-1'
          }`}
        >
          {renderContent()}
          {isCust && timeLabel && <div className="text-right text-sm text-purple-700/80 mt-0.5">{timeLabel}</div>}
        </div>

      </div>

      {isCust && (
        <div className="w-14 h-14 rounded-2xl bg-[#EEE8FC] text-purple-700 flex items-center justify-center flex-shrink-0">
          <User className="w-7 h-7" strokeWidth={1.5} />
        </div>
      )}
    </div>
  );
};
