import React from 'react';
import type { Message } from '../../../lib/types';
import { formatTime, orderCodesIn } from '../../../lib/orderView';
import { useOrder } from '../../../lib/useOrder';
import { HeadsetIcon, UserIcon } from '../../../components/icons';
import { OrderCard } from './OrderCard';

interface MessageItemProps {
  message: Message;
  onSelectClause: (clauseId: string) => void;
  onQuickPrompt: (prompt: string) => void;
  onViewPolicy: () => void;
}

const INLINE = /(\*\*[^*]+\*\*|\[POL-[A-Z0-9-]+\])/g;

/** Bold (**text**) and policy citations ([POL-...]) are the only inline formats the agent produces. */
function renderInline(text: string, onSelectClause: (id: string) => void): React.ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) return <b key={i}>{part.slice(2, -2)}</b>;
    const cite = part.match(/^\[(POL-[A-Z0-9-]+)\]$/);
    if (cite) {
      return (
        <button
          key={i}
          type="button"
          className="cite"
          title="Xem nguyên văn điều khoản chính sách"
          onClick={() => onSelectClause(cite[1])}
        >
          [{cite[1]}]
        </button>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

const MAX_ORDER_CARDS = 2;

const OrderCardFor: React.FC<{ code: string; onQuickPrompt: (p: string) => void; onViewPolicy: () => void }> = ({
  code,
  onQuickPrompt,
  onViewPolicy,
}) => {
  const state = useOrder(code);
  // No card when the order cannot be shown (not found, not verified yet): the assistant's text says why.
  if (state.status !== 'ready') return null;
  return <OrderCard order={state.order} onQuickPrompt={onQuickPrompt} onViewPolicy={onViewPolicy} />;
};

export const MessageItem: React.FC<MessageItemProps> = ({ message, onSelectClause, onQuickPrompt, onViewPolicy }) => {
  const time = formatTime(message.created_at);

  if (message.role === 'customer') {
    return (
      <div className="me">
        <div className="bb">
          {message.content}
          <span className="time">{time}</span>
        </div>
        <div className="av">
          <UserIcon />
        </div>
      </div>
    );
  }

  const isStaff = message.role === 'staff';
  const paragraphs = message.content.split(/\n{2,}/).filter((p) => p.trim());
  const orderCodes = isStaff ? [] : orderCodesIn(message.content).slice(0, MAX_ORDER_CARDS);

  return (
    <div className="bot">
      {isStaff ? (
        <div className="staff-av">
          <HeadsetIcon />
        </div>
      ) : (
        <img src="/images/ui/bot-avatar.png" alt="" />
      )}
      <div className="col">
        <div className="nm">
          {isStaff ? 'Chuyên viên ShopSupport' : 'ShopSupport AI'}
          {!isStaff && <span className="tag">AI</span>}
        </div>
        {paragraphs.map((paragraph, i) => (
          <p key={i}>{renderInline(paragraph, onSelectClause)}</p>
        ))}
        {orderCodes.map((code) => (
          <OrderCardFor key={code} code={code} onQuickPrompt={onQuickPrompt} onViewPolicy={onViewPolicy} />
        ))}
        <div className="ask">
          <span />
          <span className="time">{time}</span>
        </div>
      </div>
    </div>
  );
};
