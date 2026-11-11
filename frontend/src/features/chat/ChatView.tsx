import React, { useState, useEffect, useRef } from 'react';
import { Message, PendingAction } from '../../lib/types';
import { api } from '../../lib/api';
import { ActionCard } from './ActionCard';
import { CitationModal } from '../../components/CitationModal';
import { EvidenceUploadModal } from './EvidenceUploadModal';
import { GuestOtpModal } from './GuestOtpModal';
import {
  Send,
  Bot,
  User,
  Headphones,
  Loader2,
  ThumbsUp,
  ThumbsDown,
  Sparkles,
  ShieldCheck,
} from 'lucide-react';

interface ChatViewProps {
  conversationId: string;
  isGuest: boolean;
}

export const ChatView: React.FC<ChatViewProps> = ({ conversationId, isGuest }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [progressText, setProgressText] = useState<string | null>(null);
  const [mode, setMode] = useState<string>('ai');
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);
  const [selectedClause, setSelectedClause] = useState<string | null>(null);
  const [evidenceReturnCode, setEvidenceReturnCode] = useState<string | null>(null);
  const [isOtpModalOpen, setIsOtpModalOpen] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, progressText, pendingActions]);

  // Load conversation details
  const loadConversation = async () => {
    try {
      const data = await api.getConversation(conversationId);
      setMessages(data.messages || []);
      setMode(data.mode);
      setPendingActions(data.pending_actions || []);
    } catch (err) {
      console.error('Failed to load conversation:', err);
    }
  };

  useEffect(() => {
    loadConversation();
  }, [conversationId]);

  // Setup SSE event stream
  useEffect(() => {
    const eventSource = new EventSource(`/api/conversations/${conversationId}/events`);

    eventSource.addEventListener('turn.progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setProgressText(data.label || 'Đang xử lý...');
      } catch {
        setProgressText('Đang xử lý...');
      }
    });

    eventSource.addEventListener('tool.started', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setProgressText(data.label || `Đang thực hiện ${data.tool}...`);
      } catch {
        setProgressText('Đang xử lý nghiệp vụ...');
      }
    });

    eventSource.addEventListener('tool.finished', () => {
      setProgressText('Đang hoàn thiện nội dung phản hồi...');
    });

    eventSource.addEventListener('message.completed', (e: MessageEvent) => {
      setProgressText(null);
      try {
        const data = JSON.parse(e.data);
        const newMsg: Message = {
          id: data.id || String(Date.now()),
          seq: data.seq || 0,
          role: data.role || 'assistant',
          content: data.content || '',
          citations: data.citations || [],
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, newMsg]);
      } catch (err) {
        console.error('Error parsing message.completed event', err);
      }
    });

    eventSource.addEventListener('action.proposed', (e: MessageEvent) => {
      try {
        const action: PendingAction = JSON.parse(e.data);
        setPendingActions((prev) => {
          const exists = prev.some((a) => a.id === action.id);
          if (exists) return prev.map((a) => (a.id === action.id ? action : a));
          return [...prev, action];
        });
      } catch (err) {
        console.error('Error parsing action.proposed event', err);
      }
    });

    eventSource.addEventListener('conversation.mode_changed', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setMode(data.mode);
      } catch (err) {
        console.error('Error parsing mode_changed event', err);
      }
    });

    return () => {
      eventSource.close();
    };
  }, [conversationId]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userText = input.trim();
    setInput('');
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      seq: messages.length + 1,
      role: 'customer',
      content: userText,
      citations: [],
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setLoading(true);
    setProgressText('Đang kết nối...');

    try {
      const res = await api.sendMessage(conversationId, userText);
      if (res.assistant_message) {
        const assistantMsg: Message = {
          id: `asst-${Date.now()}`,
          seq: messages.length + 2,
          role: 'assistant',
          content: res.assistant_message,
          citations: res.citations || [],
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      }
      if (res.pending_action) {
        setPendingActions((prev) => [...prev, res.pending_action!]);
      }
    } catch (err: any) {
      console.error('Send message failed:', err);
    } finally {
      setLoading(false);
      setProgressText(null);
    }
  };

  const handleEscalate = async () => {
    try {
      await api.handoff(conversationId, 'customer_request', 'Khách hàng yêu cầu gặp nhân viên trực tiếp.');
      setMode('waiting_human');
    } catch (err) {
      console.error('Handoff error:', err);
    }
  };

  // Render message text with clickable citations
  const renderMessageContent = (msg: Message) => {
    if (msg.role !== 'assistant') {
      return <div className="whitespace-pre-wrap">{msg.content}</div>;
    }

    const citationRegex = /\[(POL-[A-Z0-9-]+)\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = citationRegex.exec(msg.content)) !== null) {
      const clauseId = match[1];
      if (match.index > lastIndex) {
        parts.push(msg.content.substring(lastIndex, match.index));
      }
      parts.push(
        <button
          key={`${clauseId}-${match.index}`}
          onClick={() => setSelectedClause(clauseId)}
          className="inline-flex items-center gap-1 mx-1 px-1.5 py-0.5 bg-emerald-100 hover:bg-emerald-200 text-emerald-800 text-xs font-mono font-semibold rounded border border-emerald-300 transition"
          title="Bấm để xem nguyên văn điều khoản chính sách"
        >
          <ShieldCheck className="w-3 h-3 text-emerald-600" />
          <span>[{clauseId}]</span>
        </button>
      );
      lastIndex = match.index + match[0].length;
    }

    if (lastIndex < msg.content.length) {
      parts.push(msg.content.substring(lastIndex));
    }

    return <div className="whitespace-pre-wrap leading-relaxed">{parts}</div>;
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-4xl mx-auto bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
      {/* Top Bar */}
      <div className="px-5 py-3.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-9 h-9 rounded-full bg-emerald-600 flex items-center justify-center text-white shadow-sm">
              <Bot className="w-5 h-5" />
            </div>
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 border-2 border-white absolute bottom-0 right-0"></span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-slate-900">Trợ lý AI ShopLab</h2>
              <span className="text-[10px] bg-emerald-100 text-emerald-800 font-semibold px-1.5 py-0.5 rounded">
                Chính thức
              </span>
            </div>
            <p className="text-xs text-slate-500">
              {mode === 'ai' ? 'Trực tuyến • Phản hồi tức thì' : 'Đang kết nối chuyên viên hỗ trợ'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isGuest && (
            <button
              onClick={() => setIsOtpModalOpen(true)}
              className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 px-3 py-1.5 rounded-lg font-medium transition"
            >
              Tra đơn bằng OTP
            </button>
          )}

          <button
            onClick={handleEscalate}
            disabled={mode !== 'ai'}
            className="flex items-center gap-1.5 text-xs text-amber-800 bg-amber-50 hover:bg-amber-100 border border-amber-200 px-3 py-1.5 rounded-lg font-medium transition disabled:opacity-50"
          >
            <Headphones className="w-3.5 h-3.5 text-amber-600" />
            <span>{mode === 'ai' ? 'Gặp nhân viên' : 'Đã yêu cầu nhân viên'}</span>
          </button>
        </div>
      </div>

      {/* Messages Stream */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
        {messages.map((msg) => {
          const isAsst = msg.role === 'assistant';
          const isStaff = msg.role === 'staff';
          const isCust = msg.role === 'customer';

          return (
            <div
              key={msg.id}
              className={`flex gap-3 ${isCust ? 'justify-end' : 'justify-start'}`}
            >
              {!isCust && (
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-white text-xs ${
                    isStaff ? 'bg-indigo-600' : 'bg-emerald-600'
                  }`}
                >
                  {isStaff ? <Headphones className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>
              )}

              <div className={`max-w-[85%] md:max-w-[75%]`}>
                {!isCust && (
                  <div className="text-[11px] font-semibold text-slate-500 mb-1 flex items-center gap-1.5">
                    <span>{isStaff ? 'Chuyên viên ShopLab' : 'Trợ lý AI'}</span>
                    {isAsst && <Sparkles className="w-3 h-3 text-emerald-600" />}
                  </div>
                )}

                <div
                  className={`p-3.5 rounded-2xl text-sm ${
                    isCust
                      ? 'bg-emerald-600 text-white rounded-tr-none'
                      : isStaff
                      ? 'bg-indigo-50 text-indigo-950 border border-indigo-200 rounded-tl-none'
                      : 'bg-slate-100 text-slate-850 rounded-tl-none border border-slate-200/60'
                  }`}
                >
                  {renderMessageContent(msg)}
                </div>

                {isAsst && (
                  <div className="flex items-center gap-2 mt-1 px-1">
                    <button
                      className="text-slate-400 hover:text-emerald-600 p-1 rounded transition"
                      title="Hữu ích"
                    >
                      <ThumbsUp className="w-3 h-3" />
                    </button>
                    <button
                      className="text-slate-400 hover:text-red-600 p-1 rounded transition"
                      title="Chưa đúng ý"
                    >
                      <ThumbsDown className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>

              {isCust && (
                <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center flex-shrink-0 text-white text-xs">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          );
        })}

        {/* Pending Actions Cards */}
        {pendingActions.map((action) => (
          <ActionCard
            key={action.id}
            action={action}
            onActionUpdated={(updated) => {
              setPendingActions((prev) =>
                prev.map((a) => (a.id === updated.id ? updated : a))
              );
            }}
            onOpenEvidenceUpload={(returnCode) => setEvidenceReturnCode(returnCode)}
          />
        ))}

        {/* Live Progress Indicator */}
        {progressText && (
          <div className="flex items-center gap-2.5 text-xs text-slate-500 py-2 px-3 bg-slate-50 rounded-xl w-fit border border-slate-200">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-600" />
            <span>{progressText}</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form */}
      <div className="p-3 md:p-4 bg-slate-50 border-t border-slate-200">
        <form onSubmit={handleSend} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              mode === 'ai'
                ? 'Nhập tin nhắn (hỏi chính sách, tra đơn, hủy hoặc trả hàng)...'
                : 'Nhân viên đang theo dõi cuộc trò chuyện này...'
            }
            className="flex-1 px-4 py-2.5 text-sm bg-white border border-slate-300 rounded-xl focus:ring-2 focus:ring-emerald-500 focus:outline-none transition shadow-inner"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2.5 rounded-xl font-medium flex items-center justify-center transition disabled:opacity-50 shadow-sm"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>

      {/* Modals */}
      <CitationModal
        clauseId={selectedClause}
        onClose={() => setSelectedClause(null)}
      />

      <EvidenceUploadModal
        returnCode={evidenceReturnCode}
        onClose={() => setEvidenceReturnCode(null)}
        onSuccess={() => {
          loadConversation();
        }}
      />

      <GuestOtpModal
        isOpen={isOtpModalOpen}
        onClose={() => setIsOtpModalOpen(false)}
        onVerified={() => {
          loadConversation();
        }}
      />
    </div>
  );
};
