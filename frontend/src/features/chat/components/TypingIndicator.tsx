import React from 'react';

interface TypingIndicatorProps {
  progressText?: string | null;
}

export const TypingIndicator: React.FC<TypingIndicatorProps> = ({ progressText }) => (
  <div className="bot">
    <img src="/images/ui/bot-avatar.png" alt="" />
    <div className="col">
      <div className="nm">
        ShopSupport AI <span className="tag">AI</span>
      </div>
      <div className="typing" role="status" aria-live="polite">
        <i />
        <i />
        <i />
        <span>{progressText || 'ShopSupport AI đang suy nghĩ...'}</span>
      </div>
    </div>
  </div>
);
