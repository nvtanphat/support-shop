import React, { useState, useEffect, useRef } from 'react';
import { Message, PendingAction } from '../../lib/types';
import { api } from '../../lib/api';
import { ActionCard } from './ActionCard';
import { CitationModal } from '../../components/CitationModal';
import { EvidenceUploadModal } from './EvidenceUploadModal';
import { GuestOtpModal } from './GuestOtpModal';
import { HeroBanner } from './components/HeroBanner';
import { MessageItem } from './components/MessageItem';
import { TypingIndicator } from './components/TypingIndicator';
import { ChatInputBar } from './components/ChatInputBar';
import { OrderContextSidebar } from './components/OrderContextSidebar';

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
  const [activeOrderCode, setActiveOrderCode] = useState<string>('SL-8F3D9K');

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, progressText, pendingActions, loading]);

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

  useEffect(() => {
    if (quickFilter === 'returns') {
      executeSendMessage('Mình muốn đổi trả đơn hàng SL-8F3D9K vì tai nghe bị lỗi.');
    } else if (quickFilter === 'contact') {
      handleEscalate();
    }
  }, [quickFilter]);

  // Setup authorized SSE event stream
  useEffect(() => {
    const guestToken = api.getGuestToken();
    const token = api.getToken();
    const params = new URLSearchParams();
    if (token) {
      params.set('token', token);
    }
    if (guestToken) {
      params.set('guest_token', guestToken);
    }
    const queryStr = params.toString();
    const sseUrl = queryStr
      ? `/api/conversations/${conversationId}/events?${queryStr}`
      : `/api/conversations/${conversationId}/events`;

    const eventSource = new EventSource(sseUrl);

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
          turn_id: data.turn_id,
        };
        setMessages((prev) => {
          // 1. Exact ID duplicate check
          if (newMsg.id && prev.some((m) => m.id === newMsg.id)) {
            return prev;
          }
          // 2. Turn ID match: upgrade optimistic assistant message to canonical message
          if (newMsg.turn_id && prev.some((m) => m.turn_id === newMsg.turn_id && m.role === 'assistant')) {
            return prev.map((m) =>
              m.turn_id === newMsg.turn_id && m.role === 'assistant' ? { ...newMsg } : m
            );
          }
          // 3. Content match for pending assistant message in current turn
          if (
            prev.some(
              (m) =>
                m.role === 'assistant' &&
                m.id.startsWith('asst-') &&
                m.content.trim() === newMsg.content.trim()
            )
          ) {
            return prev.map((m) =>
              m.role === 'assistant' &&
              m.id.startsWith('asst-') &&
              m.content.trim() === newMsg.content.trim()
                ? { ...newMsg }
                : m
            );
          }
          // 4. Sequence number duplicate check
          if (newMsg.seq && prev.some((m) => m.seq === newMsg.seq && m.role === newMsg.role)) {
            return prev;
          }
          // 5. Fallback: replace trailing optimistic assistant message
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

    const turnId = `turn-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    const userText = text.trim();
    setInput('');
    const tempUserMsg: Message = {
      id: `temp-${turnId}`,
      seq: messages.length + 1,
      role: 'customer',
      content: userText,
      citations: [],
      created_at: new Date().toISOString(),
      turn_id: turnId,
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setLoading(true);
    setProgressText('Đang kết nối...');

    const orderMatch = userText.match(/SL-[A-Z0-9]+/i);
    if (orderMatch) {
      setActiveOrderCode(orderMatch[0].toUpperCase());
    }

    try {
      const res = await api.sendMessage(conversationId, userText, turnId);
      if (res.assistant_message) {
        const assistantMsg: Message = {
          id: `asst-${turnId}`,
          seq: messages.length + 2,
          role: 'assistant',
          content: res.assistant_message,
          citations: res.citations || [],
          created_at: new Date().toISOString(),
          turn_id: turnId,
        };
        setMessages((prev) => {
          // If SSE already added the assistant message with this turn_id or identical content:
          if (
            prev.some(
              (m) =>
                m.role === 'assistant' &&
                (m.turn_id === turnId || m.content.trim() === assistantMsg.content.trim())
            )
          ) {
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
        content:
          'Dạ hiện tại hệ thống hỗ trợ đang bận hoặc có sự cố mạng. Quý khách vui lòng thử lại sau giây lát hoặc bấm Hỗ trợ khác để kết nối với chuyên viên ạ.',
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

  const handleEscalate = async () => {
    try {
      await api.handoff(conversationId, 'customer_request', 'Khách hàng yêu cầu gặp nhân viên trực tiếp.');
      setMode('waiting_human');
    } catch (err) {
      console.error('Handoff error:', err);
    }
  };

  return (
    <div className="flex gap-6 h-[calc(100vh-8.5rem)] w-full">
      {/* Left/Center Column: Chat Window */}
      <div className="flex-1 min-w-0 flex flex-col h-full bg-white rounded-3xl border border-purple-100/90 shadow-sm overflow-hidden">
        {/* Messages Stream */}
        <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5">
          <HeroBanner
            onQuickPrompt={executeSendMessage}
            onOpenOtpModal={() => setIsOtpModalOpen(true)}
            onEscalate={handleEscalate}
          />

          {messages.map((msg) => (
            <MessageItem
              key={msg.id}
              message={msg}
              onSelectClause={(clauseId) => setSelectedClause(clauseId)}
              onQuickPrompt={executeSendMessage}
            />
          ))}

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

          {loading && <TypingIndicator progressText={progressText} />}

          <div ref={messagesEndRef} />
        </div>

        {/* Floating Input Bar */}
        <ChatInputBar
          input={input}
          setInput={setInput}
          onSend={handleSend}
          onKeyDown={handleKeyDown}
          onOpenOtpModal={() => setIsOtpModalOpen(true)}
          loading={loading}
          mode={mode}
        />
      </div>

      {/* Right Column: Order and Policy Context Sidebar */}
      <OrderContextSidebar
        orderCode={activeOrderCode}
        onQuickPrompt={executeSendMessage}
        onSelectClause={(clauseId) => setSelectedClause(clauseId)}
        onOpenOtp={() => setIsOtpModalOpen(true)}
      />

      {/* Modals */}
      <CitationModal
        clauseId={selectedClause}
        onClose={() => setSelectedClause(null)}
      />

      <EvidenceUploadModal
        returnCode={evidenceReturnCode}
        onClose={() => setEvidenceReturnCode(null)}
        onSuccess={loadConversation}
      />

      <GuestOtpModal
        isOpen={isOtpModalOpen}
        onClose={() => setIsOtpModalOpen(false)}
        onVerified={loadConversation}
      />
    </div>
  );
};
