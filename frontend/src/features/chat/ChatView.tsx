import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Message, PendingAction } from '../../lib/types';
import { api } from '../../lib/api';
import { orderCodesIn } from '../../lib/orderView';
import { clearOrderCache } from '../../lib/useOrder';
import { ActionCard } from './ActionCard';
import { CitationModal } from '../../components/CitationModal';
import { PolicyListModal } from '../../components/PolicyListModal';
import { EvidenceUploadModal } from './EvidenceUploadModal';
import { GuestOtpModal } from './GuestOtpModal';
import { HeroBanner } from './components/HeroBanner';
import { MessageItem } from './components/MessageItem';
import { TypingIndicator } from './components/TypingIndicator';
import { ChatInputBar } from './components/ChatInputBar';
import { OrderContextSidebar, PolicyListState } from './components/OrderContextSidebar';

/** A one-shot command from the header; `nonce` makes repeating the same command work. */
export interface ChatCommand {
  type: 'returns' | 'contact' | 'policies' | 'lookup';
  nonce: number;
}

interface ChatViewProps {
  conversationId: string;
  isGuest: boolean;
  command?: ChatCommand | null;
}

export const ChatView: React.FC<ChatViewProps> = ({ conversationId, isGuest, command }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [progressText, setProgressText] = useState<string | null>(null);
  const [mode, setMode] = useState<string>('ai');
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);
  const [selectedClause, setSelectedClause] = useState<string | null>(null);
  const [policyListOpen, setPolicyListOpen] = useState(false);
  const [evidenceReturnCode, setEvidenceReturnCode] = useState<string | null>(null);
  const [isOtpModalOpen, setIsOtpModalOpen] = useState(false);
  const [policies, setPolicies] = useState<PolicyListState>({ status: 'loading', policies: [] });
  const [latestOrderCode, setLatestOrderCode] = useState<string | null>(null);

  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = chatRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, progressText, pendingActions, loading]);

  // Policies in force: shown in the sidebar and the "Chính sách" list.
  useEffect(() => {
    let cancelled = false;
    api
      .getPolicies()
      .then((res) => !cancelled && setPolicies({ status: 'ready', policies: res.policies }))
      .catch((err: unknown) =>
        !cancelled &&
        setPolicies({ status: 'error', policies: [], message: err instanceof Error ? err.message : 'Không tải được chính sách.' })
      );
    return () => {
      cancelled = true;
    };
  }, []);

  // A signed-in customer starts with their most recent order selected; a guest has none until one is mentioned.
  useEffect(() => {
    if (isGuest) {
      setLatestOrderCode(null);
      return;
    }
    let cancelled = false;
    api
      .getMyOrders()
      .then((res) => !cancelled && setLatestOrderCode(res.orders[0]?.order_code ?? null))
      .catch(() => !cancelled && setLatestOrderCode(null));
    return () => {
      cancelled = true;
    };
  }, [isGuest]);

  const loadConversation = useCallback(async () => {
    try {
      const data = await api.getConversation(conversationId);
      setMessages(data.messages || []);
      setMode(data.mode);
      setPendingActions(data.pending_actions || []);
    } catch (err) {
      console.error('Failed to load conversation:', err);
    }
  }, [conversationId]);

  useEffect(() => {
    loadConversation();
  }, [loadConversation]);

  // The selected order is the latest one named in the conversation, else the customer's latest order.
  const activeOrderCode = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const codes = orderCodesIn(messages[i].content);
      if (codes.length) return codes[codes.length - 1];
    }
    return latestOrderCode;
  }, [messages, latestOrderCode]);

  const citedClauseIds = useMemo(() => {
    const ids: string[] = [];
    for (let i = messages.length - 1; i >= 0; i--) {
      for (const id of messages[i].citations ?? []) if (!ids.includes(id)) ids.push(id);
    }
    return ids;
  }, [messages]);

  // Setup authorized SSE event stream
  useEffect(() => {
    const guestToken = api.getGuestToken();
    const token = api.getToken();
    const params = new URLSearchParams();
    if (token) params.set('token', token);
    if (guestToken) params.set('guest_token', guestToken);
    const queryStr = params.toString();
    const sseUrl = queryStr
      ? `/api/conversations/${conversationId}/events?${queryStr}`
      : `/api/conversations/${conversationId}/events`;

    const eventSource = new EventSource(sseUrl);

    eventSource.addEventListener('turn.progress', (e: MessageEvent) => {
      try {
        setProgressText(JSON.parse(e.data).label || 'Đang xử lý...');
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
          if (newMsg.id && prev.some((m) => m.id === newMsg.id)) return prev;
          // 2. Turn ID match: upgrade optimistic assistant message to canonical message
          if (newMsg.turn_id && prev.some((m) => m.turn_id === newMsg.turn_id && m.role === 'assistant')) {
            return prev.map((m) => (m.turn_id === newMsg.turn_id && m.role === 'assistant' ? { ...newMsg } : m));
          }
          // 3. Content match for pending assistant message in current turn
          if (prev.some((m) => m.role === 'assistant' && m.id.startsWith('asst-') && m.content.trim() === newMsg.content.trim())) {
            return prev.map((m) =>
              m.role === 'assistant' && m.id.startsWith('asst-') && m.content.trim() === newMsg.content.trim() ? { ...newMsg } : m
            );
          }
          // 4. Sequence number duplicate check
          if (newMsg.seq && prev.some((m) => m.seq === newMsg.seq && m.role === newMsg.role)) return prev;
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
        setMode(JSON.parse(e.data).mode);
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
    clearOrderCache(); // an order may change during the turn (confirmed return, cancellation)

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
          if (prev.some((m) => m.role === 'assistant' && (m.turn_id === turnId || m.content.trim() === assistantMsg.content.trim()))) {
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
    } catch (err: unknown) {
      console.error('Send message failed:', err);
      const errMsg: Message = {
        id: `err-${Date.now()}`,
        seq: messages.length + 2,
        role: 'assistant',
        content:
          'Dạ hiện tại hệ thống hỗ trợ đang bận hoặc có sự cố mạng. Quý khách vui lòng thử lại sau giây lát hoặc bấm Liên hệ để kết nối với chuyên viên ạ.',
        citations: [],
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
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

  // Header commands. The refs keep the latest handlers without re-running the effect on every render.
  const sendRef = useRef(executeSendMessage);
  sendRef.current = executeSendMessage;
  const escalateRef = useRef(handleEscalate);
  escalateRef.current = handleEscalate;
  useEffect(() => {
    if (!command) return;
    if (command.type === 'returns') sendRef.current('Mình muốn đổi trả / hoàn tiền');
    else if (command.type === 'contact') escalateRef.current();
    else if (command.type === 'policies') setPolicyListOpen(true);
    else if (command.type === 'lookup') setIsOtpModalOpen(true);
  }, [command]);

  const openReturnPolicy = () => {
    const returnClause = policies.policies.find((p) => p.topic === 'return');
    if (returnClause) setSelectedClause(returnClause.clause_id);
    else setPolicyListOpen(true);
  };

  return (
    <main>
      <section className="left">
        <HeroBanner onQuickPrompt={executeSendMessage} />

        <div className="chat" ref={chatRef} aria-live="polite">
          {messages.map((msg) => (
            <MessageItem
              key={msg.id}
              message={msg}
              onSelectClause={setSelectedClause}
              onQuickPrompt={executeSendMessage}
              onViewPolicy={openReturnPolicy}
            />
          ))}

          {pendingActions.map((action) => (
            <div key={action.id} className="cardwrap">
              <ActionCard
                action={action}
                onActionUpdated={(updated) => {
                  setPendingActions((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
                  clearOrderCache();
                }}
                onOpenEvidenceUpload={(returnCode) => setEvidenceReturnCode(returnCode)}
              />
            </div>
          ))}

          {loading && <TypingIndicator progressText={progressText} />}
        </div>

        <ChatInputBar
          input={input}
          setInput={setInput}
          onSend={() => executeSendMessage(input)}
          onOpenOtpModal={() => setIsOtpModalOpen(true)}
          loading={loading}
          mode={mode}
        />
      </section>

      <OrderContextSidebar
        orderCode={activeOrderCode}
        policies={policies}
        citedClauseIds={citedClauseIds}
        isGuest={isGuest}
        onQuickPrompt={executeSendMessage}
        onSelectClause={setSelectedClause}
        onOpenOtp={() => setIsOtpModalOpen(true)}
      />

      {/* Modals are Tailwind-styled, so they live outside the `.ss` design scope. */}
      {createPortal(
        <>
          <CitationModal clauseId={selectedClause} onClose={() => setSelectedClause(null)} />
          <PolicyListModal
            open={policyListOpen}
            policies={policies.policies}
            loading={policies.status === 'loading'}
            error={policies.status === 'error' ? policies.message : undefined}
            onSelect={(id) => {
              setPolicyListOpen(false);
              setSelectedClause(id);
            }}
            onClose={() => setPolicyListOpen(false)}
          />
          <EvidenceUploadModal returnCode={evidenceReturnCode} onClose={() => setEvidenceReturnCode(null)} onSuccess={loadConversation} />
          <GuestOtpModal
            isOpen={isOtpModalOpen}
            onClose={() => setIsOtpModalOpen(false)}
            onVerified={loadConversation}
            defaultOrderCode={activeOrderCode}
          />
        </>,
        document.body
      )}
    </main>
  );
};
