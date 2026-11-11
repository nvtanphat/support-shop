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
  Sparkles,
  ShieldCheck,
  Plus,
  Mic,
  Zap,
  Package,
  FileText,
  HelpCircle,
  Check,
  RotateCcw,
  BookOpen,
  ChevronRight,
  Info,
  Calendar,
  CreditCard,
  Truck,
} from 'lucide-react';

interface ChatViewProps {
  conversationId: string;
  isGuest: boolean;
  quickFilter?: 'returns' | 'contact';
}

export const ChatView: React.FC<ChatViewProps> = ({ conversationId, isGuest: _isGuest, quickFilter }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [progressText, setProgressText] = useState<string | null>(null);
  const [mode, setMode] = useState<string>('ai');
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);
  const [selectedClause, setSelectedClause] = useState<string | null>(null);
  const [evidenceReturnCode, setEvidenceReturnCode] = useState<string | null>(null);
  const [isOtpModalOpen, setIsOtpModalOpen] = useState(false);

  // Active focus order for right sidebar preview (default to SL-8F3D9K)
  const [activeOrderCode, setActiveOrderCode] = useState<string>('SL-8F3D9K');

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

  // Handle external quickFilter from Header
  useEffect(() => {
    if (quickFilter === 'returns') {
      handleQuickPrompt('Mình muốn đổi trả đơn hàng SL-8F3D9K vì tai nghe bị lỗi.');
    } else if (quickFilter === 'contact') {
      handleEscalate();
    }
  }, [quickFilter]);

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
          id: data.id || `msg-${Date.now()}`,
          seq: data.seq || 0,
          role: data.role || 'assistant',
          content: data.content || '',
          citations: data.citations || [],
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => {
          // Avoid duplicate by message ID or exact seq
          if (newMsg.id && prev.some((m) => m.id === newMsg.id)) {
            return prev;
          }
          if (newMsg.seq && prev.some((m) => m.seq === newMsg.seq && m.role === newMsg.role)) {
            return prev;
          }
          // If the last message was a temp assistant message added by REST, replace it
          const lastIdx = prev.length - 1;
          if (lastIdx >= 0 && prev[lastIdx].id.startsWith('asst-') && prev[lastIdx].role === 'assistant') {
            const updated = [...prev];
            updated[lastIdx] = newMsg;
            return updated;
          }
          return [...prev, newMsg];
        });
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

  const executeSendMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    const userText = text.trim();
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

    // Extract potential order code
    const orderMatch = userText.match(/SL-[A-Z0-9]+/i);
    if (orderMatch) {
      setActiveOrderCode(orderMatch[0].toUpperCase());
    }

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
        setMessages((prev) => {
          // If SSE already added this response as the last message, don't duplicate
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.role === 'assistant' && lastMsg.content === assistantMsg.content) {
            return prev;
          }
          return [...prev, assistantMsg];
        });
      }
      if (res.pending_action) {
        setPendingActions((prev) => {
          const exists = prev.some((a) => a.id === res.pending_action!.id);
          if (exists) return prev;
          return [...prev, res.pending_action!];
        });
      }
    } catch (err: any) {
      console.error('Send message failed:', err);
      const errMsg: Message = {
        id: `err-${Date.now()}`,
        seq: messages.length + 2,
        role: 'assistant',
        content: 'Dạ hiện tại hệ thống hỗ trợ đang bận tạm thời hoặc có sự cố mạng. Quý khách vui lòng thử lại sau giây lát hoặc bấm Hỗ trợ khác để kết nối với chuyên viên ạ.',
        citations: [],
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
      setProgressText(null);
    }
  };

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    executeSendMessage(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      executeSendMessage(input);
    }
  };

  const handleQuickPrompt = (prompt: string) => {
    executeSendMessage(prompt);
  };

  const handleEscalate = async () => {
    try {
      await api.handoff(conversationId, 'customer_request', 'Khách hàng yêu cầu gặp nhân viên trực tiếp.');
      setMode('waiting_human');
    } catch (err) {
      console.error('Handoff error:', err);
    }
  };

  // Render message text with rich citations and order embeds
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
          className="inline-flex items-center gap-1 mx-1 px-2 py-0.5 bg-purple-100 hover:bg-purple-200 text-purple-800 text-xs font-mono font-semibold rounded-md border border-purple-300 transition shadow-2xs"
          title="Bấm để xem nguyên văn điều khoản chính sách"
        >
          <ShieldCheck className="w-3 h-3 text-purple-600" />
          <span>[{clauseId}]</span>
        </button>
      );
      lastIndex = match.index + match[0].length;
    }

    if (lastIndex < msg.content.length) {
      parts.push(msg.content.substring(lastIndex));
    }

    // Check if this message mentions order SL-8F3D9K to render the interactive embedded order card
    const hasOrderEmbed = msg.content.includes('SL-8F3D9K') || msg.content.includes('8F3D9K');

    return (
      <div className="space-y-3">
        <div className="whitespace-pre-wrap leading-relaxed">{parts}</div>

        {/* Embedded Interactive Order Card matching design screenshot */}
        {hasOrderEmbed && (
          <div className="mt-3 p-4 bg-white rounded-2xl border border-purple-100/90 shadow-sm space-y-3.5">
            {/* Product snippet */}
            <div className="flex items-center gap-3.5">
              <div className="w-14 h-14 rounded-xl bg-purple-50 border border-purple-100 flex items-center justify-center p-2 flex-shrink-0">
                <img
                  src="https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=150&auto=format&fit=crop&q=80"
                  alt="Tai nghe không dây Studio Pro"
                  className="w-full h-full object-contain rounded-lg"
                  onError={(e) => {
                    // Fallback icon if image doesn't load offline
                    (e.target as HTMLElement).style.display = 'none';
                  }}
                />
              </div>
              <div className="flex-1 min-w-0">
                <h4 className="font-bold text-slate-900 text-sm truncate">
                  Tai nghe không dây Studio Pro
                </h4>
                <div className="flex flex-wrap items-center gap-x-2 text-xs text-slate-500 mt-0.5">
                  <span>Mã đơn: <strong className="font-mono text-purple-700">SL-8F3D9K</strong></span>
                  <span>•</span>
                  <span>Ngày đặt: 08/11/2026</span>
                  <span>•</span>
                  <span>Số lượng: <strong className="text-slate-800">x1</strong></span>
                  <span>•</span>
                  <span>Tổng tiền: <strong className="text-slate-900">1.290.000 đ</strong></span>
                </div>
              </div>
            </div>

            {/* Stepper timeline */}
            <div className="pt-2 border-t border-slate-100">
              <div className="grid grid-cols-4 gap-2 text-center text-[11px]">
                <div className="flex flex-col items-center">
                  <div className="w-6 h-6 rounded-full bg-purple-600 text-white flex items-center justify-center mb-1">
                    <Check className="w-3.5 h-3.5 stroke-[3]" />
                  </div>
                  <span className="font-semibold text-slate-800">Đã đặt hàng</span>
                  <span className="text-[10px] text-slate-400">08/11</span>
                </div>

                <div className="flex flex-col items-center">
                  <div className="w-6 h-6 rounded-full bg-purple-600 text-white flex items-center justify-center mb-1">
                    <Check className="w-3.5 h-3.5 stroke-[3]" />
                  </div>
                  <span className="font-semibold text-slate-800">Đang chuẩn bị</span>
                  <span className="text-[10px] text-slate-400">08/11</span>
                </div>

                <div className="flex flex-col items-center">
                  <div className="w-6 h-6 rounded-full bg-purple-600 text-white flex items-center justify-center mb-1">
                    <Check className="w-3.5 h-3.5 stroke-[3]" />
                  </div>
                  <span className="font-semibold text-slate-800">Đang giao</span>
                  <span className="text-[10px] text-slate-400">09/11</span>
                </div>

                <div className="flex flex-col items-center">
                  <div className="w-6 h-6 rounded-full bg-emerald-500 text-white flex items-center justify-center mb-1 shadow-xs">
                    <Check className="w-3.5 h-3.5 stroke-[3]" />
                  </div>
                  <span className="font-bold text-emerald-700">Đã giao</span>
                  <span className="text-[10px] text-emerald-600 font-medium">10/11</span>
                </div>
              </div>
            </div>

            {/* Eligibility Info Box */}
            <div className="p-3 bg-purple-50/70 border border-purple-100 rounded-xl text-xs space-y-1 text-slate-700">
              <div className="flex items-center gap-1.5 font-bold text-purple-900">
                <Info className="w-4 h-4 text-purple-600 flex-shrink-0" />
                <span>Bạn có thể đổi trả sản phẩm này.</span>
              </div>
              <ul className="pl-5 space-y-0.5 list-disc text-slate-600 text-[11px]">
                <li>Thời hạn đổi trả: trong 7 ngày kể từ ngày nhận hàng (đến hết 23:59 ngày 17/11/2026).</li>
                <li>Điều kiện: sản phẩm bị lỗi kỹ thuật, còn nguyên tem và phụ kiện.</li>
              </ul>
            </div>

            {/* Quick Action Prompt Buttons */}
            <div className="pt-1 flex flex-wrap gap-2">
              <button
                onClick={() => handleQuickPrompt('Tạo yêu cầu đổi trả đơn hàng SL-8F3D9K')}
                className="px-3.5 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-purple-200 transition"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Tạo yêu cầu đổi trả</span>
              </button>

              <button
                onClick={() => setSelectedClause('POL-RET-ELIG')}
                className="px-3.5 py-2 bg-white hover:bg-purple-50 text-purple-700 border border-purple-200 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition"
              >
                <FileText className="w-3.5 h-3.5 text-purple-600" />
                <span>Xem chi tiết chính sách</span>
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex gap-6 h-[calc(100vh-8.5rem)] w-full">
      
      {/* =========================================================================
          LEFT / CENTER COLUMN: MAIN CHAT VIEW (EXPANSIVE & INDEPENDENT SCROLL)
         ========================================================================= */}
      <div className="flex-1 min-w-0 flex flex-col h-full bg-white rounded-3xl border border-purple-100/90 shadow-sm overflow-hidden">
        
        {/* Messages Stream & Welcome Header with independent scroll */}
        <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5">
          
          {/* Welcome Hero Banner Card (Exact match to reference UI) */}
          <div className="bg-gradient-to-r from-purple-100/80 via-purple-50 to-white rounded-3xl p-6 border border-purple-200/50 relative overflow-hidden shadow-xs">
            
            {/* Robot 3D Avatar Illustration on the Right */}
            <div className="absolute right-4 top-1/2 -translate-y-1/2 hidden sm:block w-36 h-36 pointer-events-none select-none">
              <div className="w-full h-full relative flex items-center justify-center">
                {/* Glowing aura */}
                <div className="absolute w-28 h-28 rounded-full bg-purple-300/40 blur-xl"></div>
                {/* Robot stylized vector illustration */}
                <svg viewBox="0 0 200 200" className="w-32 h-32 relative z-10 drop-shadow-md">
                  <circle cx="100" cy="95" r="55" fill="#FFFFFF" stroke="#DDD6FE" strokeWidth="4" />
                  <rect x="65" y="70" width="70" height="46" rx="23" fill="#1E1B4B" />
                  <ellipse cx="85" cy="92" rx="8" ry="11" fill="#A855F7" />
                  <ellipse cx="115" cy="92" rx="8" ry="11" fill="#A855F7" />
                  <path d="M 94 105 Q 100 110 106 105" stroke="#DDD6FE" strokeWidth="3" fill="none" strokeLinecap="round" />
                  {/* Headphones */}
                  <path d="M 40 95 A 60 60 0 0 1 160 95" fill="none" stroke="#7C3AED" strokeWidth="8" strokeLinecap="round" />
                  <rect x="34" y="80" width="14" height="32" rx="7" fill="#6D28D9" />
                  <rect x="152" y="80" width="14" height="32" rx="7" fill="#6D28D9" />
                  {/* Shopping bags beside robot */}
                  <rect x="145" y="115" width="28" height="34" rx="4" fill="#C084FC" />
                  <path d="M 152 115 A 7 7 0 0 1 166 115" fill="none" stroke="#FFFFFF" strokeWidth="2.5" />
                  <rect x="165" y="122" width="24" height="28" rx="4" fill="#F472B6" />
                </svg>
              </div>
            </div>

            <div className="max-w-lg relative z-10 space-y-3">
              <h1 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2">
                <span>Xin chào!</span>
                <span className="text-2xl">👋</span>
              </h1>
              <p className="text-xs md:text-sm text-slate-600 leading-relaxed">
                Tôi là trợ lý AI của ShopSupport, sẵn sàng hỗ trợ bạn 24/7 về đơn hàng, chính sách, đổi trả và các vấn đề khác.
              </p>

              {/* 4 Quick prompt chips */}
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  onClick={() => setIsOtpModalOpen(true)}
                  className="px-3.5 py-2 bg-white/90 hover:bg-white text-slate-700 hover:text-purple-700 rounded-2xl text-xs font-semibold flex items-center gap-1.5 border border-purple-200/80 shadow-xs transition hover:shadow-sm"
                >
                  <Zap className="w-3.5 h-3.5 text-purple-600" />
                  <span>Tra cứu đơn hàng</span>
                </button>

                <button
                  onClick={() => handleQuickPrompt('Mình muốn đổi trả đơn hàng SL-8F3D9K vì tai nghe bị lỗi.')}
                  className="px-3.5 py-2 bg-white/90 hover:bg-white text-slate-700 hover:text-purple-700 rounded-2xl text-xs font-semibold flex items-center gap-1.5 border border-purple-200/80 shadow-xs transition hover:shadow-sm"
                >
                  <Package className="w-3.5 h-3.5 text-purple-600" />
                  <span>Đổi trả / Hoàn tiền</span>
                </button>

                <button
                  onClick={() => handleQuickPrompt('Chính sách đổi trả hàng tại shop quy định như thế nào?')}
                  className="px-3.5 py-2 bg-white/90 hover:bg-white text-slate-700 hover:text-purple-700 rounded-2xl text-xs font-semibold flex items-center gap-1.5 border border-purple-200/80 shadow-xs transition hover:shadow-sm"
                >
                  <FileText className="w-3.5 h-3.5 text-purple-600" />
                  <span>Hỏi về chính sách</span>
                </button>

                <button
                  onClick={handleEscalate}
                  className="px-3.5 py-2 bg-white/90 hover:bg-white text-slate-700 hover:text-purple-700 rounded-2xl text-xs font-semibold flex items-center gap-1.5 border border-purple-200/80 shadow-xs transition hover:shadow-sm"
                >
                  <HelpCircle className="w-3.5 h-3.5 text-purple-600" />
                  <span>Hỗ trợ khác</span>
                </button>
              </div>
            </div>
          </div>

          {/* Conversation Messages */}
          {messages.map((msg) => {
            const isAsst = msg.role === 'assistant';
            const isStaff = msg.role === 'staff';
            const isCust = msg.role === 'customer';

            return (
              <div
                key={msg.id}
                className={`flex gap-3 items-end ${isCust ? 'justify-end' : 'justify-start'}`}
              >
                {!isCust && (
                  <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-500 text-white flex items-center justify-center flex-shrink-0 shadow-sm mb-1">
                    {isStaff ? <Headphones className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
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
                    {renderMessageContent(msg)}
                  </div>

                  <div className={`text-[10px] text-slate-400 px-2 ${isCust ? 'text-right' : 'text-left'}`}>
                    {msg.created_at
                      ? new Date(msg.created_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
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
          })}

          {/* Pending Action Proposals embedded inside chat stream */}
          {pendingActions.map((action) => (
            <div key={action.id} className="max-w-2xl mx-auto">
              <ActionCard
                action={action}
                onActionUpdated={(updated) => {
                  setPendingActions((prev) =>
                    prev.map((a) => (a.id === updated.id ? updated : a))
                  );
                }}
                onOpenEvidenceUpload={(returnCode) => setEvidenceReturnCode(returnCode)}
              />
            </div>
          ))}

          {/* Active AI Processing / Typing Indicator Bubble */}
          {loading && (
            <div className="flex gap-3 items-end justify-start">
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-500 text-white flex items-center justify-center flex-shrink-0 shadow-sm mb-1">
                <Bot className="w-5 h-5 animate-pulse" />
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
                    {progressText || 'ShopSupport AI đang xử lý...'}
                  </span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* =========================================================================
            BOTTOM FLOATING INPUT BAR (EXACT MATCH TO DESIGN SCREENSHOT)
           ========================================================================= */}
        <div className="p-3 md:p-4 bg-white/90 backdrop-blur-md border-t border-purple-100">
          <form
            onSubmit={handleSend}
            className="flex items-center gap-2 bg-white rounded-2xl border border-purple-200/80 px-2.5 py-1.5 shadow-sm focus-within:ring-2 focus-within:ring-purple-400 focus-within:border-transparent transition"
          >
            {/* Plus Button */}
            <button
              type="button"
              onClick={() => setIsOtpModalOpen(true)}
              className="w-10 h-10 rounded-xl bg-purple-50 hover:bg-purple-100 text-purple-600 flex items-center justify-center transition flex-shrink-0"
              title="Tra cứu hoặc thao tác thêm"
            >
              <Plus className="w-5 h-5" />
            </button>

            {/* Main Text Input */}
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
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
      </div>

      {/* =========================================================================
          RIGHT COLUMN: ORDER CONTEXT & RELATED POLICIES (MATCHING DESIGN SCREENSHOT)
         ========================================================================= */}
      <div className="w-80 xl:w-96 hidden lg:flex flex-col gap-5 h-full overflow-y-auto">
        
        {/* Card 1: Order Details (Đơn hàng SL-8F3D9K) */}
        <div className="bg-white rounded-3xl p-5 border border-purple-100 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Package className="w-5 h-5 text-purple-600" />
              <h3 className="font-bold text-slate-900 text-sm">
                Đơn hàng {activeOrderCode}
              </h3>
            </div>
            <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-semibold px-2.5 py-0.5 rounded-full flex items-center gap-1">
              <Check className="w-3 h-3 stroke-[3]" />
              <span>Đã giao</span>
            </span>
          </div>

          {/* Product row */}
          <div className="flex items-center gap-3 pt-1">
            <div className="w-14 h-14 rounded-2xl bg-purple-50 border border-purple-100 flex items-center justify-center p-2 flex-shrink-0">
              <img
                src="https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=150&auto=format&fit=crop&q=80"
                alt="Tai nghe không dây Studio Pro"
                className="w-full h-full object-contain rounded-lg"
              />
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="font-bold text-slate-900 text-xs truncate">
                Tai nghe không dây Studio Pro
              </h4>
              <div className="flex items-center justify-between text-xs text-slate-500 mt-1">
                <span>x1</span>
                <span className="font-bold text-slate-900">1.290.000 đ</span>
              </div>
            </div>
          </div>

          {/* Meta rows */}
          <div className="space-y-2 text-xs pt-2 border-t border-slate-100">
            <div className="flex items-center justify-between text-slate-600">
              <span className="flex items-center gap-1.5 text-slate-400">
                <Calendar className="w-3.5 h-3.5" />
                <span>Ngày đặt hàng</span>
              </span>
              <span className="font-semibold text-slate-800">08/11/2026</span>
            </div>

            <div className="flex items-center justify-between text-slate-600">
              <span className="flex items-center gap-1.5 text-slate-400">
                <Truck className="w-3.5 h-3.5" />
                <span>Ngày giao hàng</span>
              </span>
              <span className="font-semibold text-slate-800">10/11/2026</span>
            </div>

            <div className="flex items-center justify-between text-slate-600">
              <span className="flex items-center gap-1.5 text-slate-400">
                <CreditCard className="w-3.5 h-3.5" />
                <span>Phương thức thanh toán</span>
              </span>
              <span className="font-medium text-slate-800">Thanh toán khi nhận hàng</span>
            </div>
          </div>

          {/* Action button */}
          <button
            onClick={() => handleQuickPrompt(`Tạo yêu cầu đổi trả cho đơn hàng ${activeOrderCode}`)}
            className="w-full py-2.5 px-4 rounded-xl border-2 border-purple-600 text-purple-700 hover:bg-purple-50 font-bold text-xs flex items-center justify-center gap-2 transition"
          >
            <RotateCcw className="w-4 h-4 text-purple-600" />
            <span>Yêu cầu đổi trả</span>
          </button>
        </div>

        {/* Card 2: Related Policies (Chính sách liên quan) */}
        <div className="bg-white rounded-3xl p-5 border border-purple-100 shadow-sm space-y-3">
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-purple-600" />
            <h3 className="font-bold text-slate-900 text-sm">
              Chính sách liên quan
            </h3>
          </div>

          <div className="space-y-1.5 pt-1">
            <button
              onClick={() => setSelectedClause('POL-RET-ELIG')}
              className="w-full p-2.5 rounded-xl hover:bg-purple-50/70 text-left text-xs font-semibold text-slate-700 hover:text-purple-800 flex items-center justify-between transition group"
            >
              <div className="flex items-center gap-2 truncate">
                <FileText className="w-3.5 h-3.5 text-purple-500 group-hover:text-purple-700 flex-shrink-0" />
                <span className="truncate">Điều kiện đổi trả</span>
              </div>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-700 flex-shrink-0" />
            </button>

            <button
              onClick={() => setSelectedClause('POL-RET-TIME')}
              className="w-full p-2.5 rounded-xl hover:bg-purple-50/70 text-left text-xs font-semibold text-slate-700 hover:text-purple-800 flex items-center justify-between transition group"
            >
              <div className="flex items-center gap-2 truncate">
                <FileText className="w-3.5 h-3.5 text-purple-500 group-hover:text-purple-700 flex-shrink-0" />
                <span className="truncate">Thời hạn và quy trình đổi trả</span>
              </div>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-700 flex-shrink-0" />
            </button>

            <button
              onClick={() => setSelectedClause('POL-RET-EXCL')}
              className="w-full p-2.5 rounded-xl hover:bg-purple-50/70 text-left text-xs font-semibold text-slate-700 hover:text-purple-800 flex items-center justify-between transition group"
            >
              <div className="flex items-center gap-2 truncate">
                <FileText className="w-3.5 h-3.5 text-purple-500 group-hover:text-purple-700 flex-shrink-0" />
                <span className="truncate">Các trường hợp không được đổi trả</span>
              </div>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-700 flex-shrink-0" />
            </button>
          </div>
        </div>

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
