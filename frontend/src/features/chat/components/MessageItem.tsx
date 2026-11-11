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
          <ShieldCheck className="w-3 h-3 text-purple-600" />
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

  return (
    <div className={`flex gap-3 items-end ${isCust ? 'justify-end' : 'justify-start'}`}>
      {!isCust && (
        <div className="w-10 h-10 rounded-2xl overflow-hidden flex items-center justify-center flex-shrink-0 shadow-sm mb-1 bg-purple-50 border border-purple-100">
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

      <div className="max-w-[85%] md:max-w-[80%] space-y-1">
        {!isCust && (
          <div className="flex items-center gap-2 px-1 text-xs">
            <span className="font-bold text-slate-900">
              {isStaff ? 'Chuyên viên ShopSupport' : 'ShopSupport AI'}
            </span>
            {isAsst && (
              <span className="bg-purple-600 text-white text-[10px] font-extrabold px-1.5 py-0.5 rounded-md flex items-center gap-1">
                <Sparkles className="w-2.5 h-2.5" />
                <span>AI</span>
              </span>
            )}
          </div>
        )}

        <div
          className={`p-4 rounded-3xl text-sm ${
            isCust
              ? 'bg-purple-50 text-slate-900 border border-purple-200/70 rounded-br-xs shadow-xs'
              : isStaff
              ? 'bg-indigo-50 text-indigo-950 border border-indigo-200 rounded-bl-xs shadow-xs'
              : 'bg-white text-slate-800 border border-slate-200/80 rounded-bl-xs shadow-xs'
          }`}
        >
          {renderContent()}
        </div>

        <div className={`text-[10px] text-slate-400 px-2 ${isCust ? 'text-right' : 'text-left'}`}>
          {message.created_at
            ? new Date(message.created_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
            : ''}
        </div>
      </div>

      {isCust && (
        <div className="w-10 h-10 rounded-2xl bg-purple-100 text-purple-700 flex items-center justify-center flex-shrink-0 border border-purple-200 mb-1">
          <User className="w-5 h-5" />
        </div>
      )}
    </div>
  );
};
