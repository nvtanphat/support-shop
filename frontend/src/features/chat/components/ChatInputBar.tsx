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
    <div className="p-3 md:p-4 bg-white/90 backdrop-blur-md border-t border-purple-100">
      <form
        onSubmit={onSend}
        className="flex items-center gap-2 bg-white rounded-2xl border border-purple-200/80 px-2.5 py-1.5 shadow-sm focus-within:ring-2 focus-within:ring-purple-400 focus-within:border-transparent transition"
      >
        {/* Plus Button */}
        <button
          type="button"
          onClick={onOpenOtpModal}
          className="w-10 h-10 rounded-xl bg-purple-50 hover:bg-purple-100 text-purple-600 flex items-center justify-center transition flex-shrink-0"
          title="Tra cứu đơn hàng hoặc xác minh OTP"
        >
          <Plus className="w-5 h-5" />
        </button>

        {/* Main Text Input */}
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
          className="flex-1 px-3 py-2 text-sm bg-transparent border-none focus:outline-none text-slate-800 placeholder-slate-400"
        />

        {/* Shortcut Badge */}
        <span className="hidden lg:inline-flex text-[11px] font-semibold text-slate-400 bg-slate-100 px-2.5 py-1 rounded-lg">
          Ctrl + Enter Gửi nhanh
        </span>

        {/* Mic Button */}
        <button
          type="button"
          className="w-9 h-9 rounded-xl hover:bg-purple-50 text-slate-400 hover:text-purple-600 flex items-center justify-center transition flex-shrink-0"
          title="Nhập bằng giọng nói"
        >
          <Mic className="w-5 h-5" />
        </button>

        {/* Send Button */}
        <button
          type="submit"
          disabled={!input.trim() || loading}
          className="w-10 h-10 rounded-xl bg-purple-600 hover:bg-purple-700 text-white flex items-center justify-center shadow-md shadow-purple-200 transition disabled:opacity-40 flex-shrink-0"
          title="Gửi tin nhắn"
        >
          <Send className="w-4 h-4 -rotate-12" />
        </button>
      </form>
    </div>
  );
};
