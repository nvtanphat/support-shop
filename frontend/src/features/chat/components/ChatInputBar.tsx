import React from 'react';
import { Plus, Mic, Send } from 'lucide-react';

interface ChatInputBarProps {
  input: string;
  setInput: (value: string) => void;
  onSend: (e: React.FormEvent) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  onOpenOtpModal: () => void;
  loading: boolean;
  mode: string;
}

export const ChatInputBar: React.FC<ChatInputBarProps> = ({
  input,
  setInput,
  onSend,
  onKeyDown,
  onOpenOtpModal,
  loading,
  mode,
}) => {
  return (
    <div className="px-6 md:px-10 py-2.5 bg-white/90 backdrop-blur-md">
      <div className="flex items-center gap-3">
        {/* Plus Button */}
        <button
          type="button"
          onClick={onOpenOtpModal}
          className="w-14 h-14 rounded-2xl bg-white hover:bg-[#F7F3FF] text-slate-900 flex items-center justify-center transition flex-shrink-0 shadow-pill"
          title="Tra cứu đơn hàng hoặc xác minh OTP"
        >
          <Plus className="w-6 h-6" />
        </button>

        <form
          onSubmit={onSend}
          className="flex-1 flex items-center gap-3 bg-white rounded-[22px] border-2 border-purple-700 pl-5 pr-2 py-1.5 shadow-[0_0_0_4px_rgba(167,139,250,0.22),0_10px_28px_-12px_rgba(109,40,217,0.4)] transition"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={
              mode === 'ai'
                ? 'Nhập câu hỏi hoặc yêu cầu hỗ trợ...'
                : 'Nhân viên đang tiếp nhận cuộc trò chuyện này...'
            }
            className="flex-1 py-2.5 text-base bg-transparent border-none focus:outline-none text-slate-900 placeholder-slate-500"
          />

          <span className="hidden lg:inline-flex items-center gap-2 text-sm text-slate-600">
            <kbd className="font-sans px-2.5 py-1 rounded-lg bg-[#F1EEF8] text-slate-700 text-xs font-medium">Ctrl + Enter</kbd>
            <span>Gửi nhanh</span>
          </span>

          <button
            type="button"
            className="w-10 h-10 rounded-xl hover:bg-purple-50 text-purple-700 flex items-center justify-center transition flex-shrink-0"
            title="Nhập bằng giọng nói"
          >
            <Mic className="w-6 h-6" />
          </button>

          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#6D28D9] to-[#4C1D95] hover:from-[#5B21B6] hover:to-[#3B0F8C] text-white flex items-center justify-center shadow-cta transition disabled:cursor-not-allowed flex-shrink-0"
            title="Gửi tin nhắn"
          >
            <Send className="w-6 h-6 -rotate-12" />
          </button>
        </form>
      </div>
    </div>
  );
};
