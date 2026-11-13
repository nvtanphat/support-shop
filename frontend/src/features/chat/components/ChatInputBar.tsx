import React from 'react';
import { MicIcon, PlusIcon, SendIcon } from '../../../components/icons';

interface ChatInputBarProps {
  input: string;
  setInput: (value: string) => void;
  onSend: () => void;
  onOpenOtpModal: () => void;
  loading: boolean;
  mode: string;
}

export const ChatInputBar: React.FC<ChatInputBarProps> = ({ input, setInput, onSend, onOpenOtpModal, loading, mode }) => {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Enter and Ctrl/Cmd+Enter both send; never while an IME composition is still being confirmed.
    if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="composer">
      <button
        type="button"
        className="plus"
        aria-label="Xác minh đơn hàng"
        title="Tra cứu đơn hàng hoặc xác minh OTP"
        onClick={onOpenOtpModal}
      >
        <PlusIcon />
      </button>
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault();
          onSend();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={mode === 'ai' ? 'Nhập câu hỏi hoặc yêu cầu hỗ trợ...' : 'Nhân viên đang tiếp nhận cuộc trò chuyện này...'}
          autoComplete="off"
        />
        <button type="button" className="mic" aria-label="Ghi âm (chưa hỗ trợ)" aria-disabled="true" title="Chưa hỗ trợ ghi âm">
          <MicIcon />
        </button>
        <button type="submit" className="send" aria-label="Gửi" disabled={!input.trim() || loading}>
          <SendIcon />
        </button>
      </form>
    </div>
  );
};
