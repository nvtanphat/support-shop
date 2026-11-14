import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { LogIn } from 'lucide-react';
import { ChatView, ChatCommand } from '../features/chat/ChatView';
import { StaffPortal } from '../features/staff/StaffPortal';
import { api, SESSION_EXPIRED_EVENT } from '../lib/api';
import { useEscapeKey } from '../lib/useEscapeKey';
import {
  CartIcon,
  ChatIcon,
  OrderLookupIcon,
  ReceiptIcon,
  RefreshIcon,
  SearchIcon,
  SupportIcon,
  UserIcon,
} from '../components/icons';

type Tab = 'assistant' | 'staff';

const CONVERSATION_KEY = 'conversation_id';

function readSavedConversation(): string | null {
  try {
    return localStorage.getItem(CONVERSATION_KEY);
  } catch {
    return null;
  }
}

function saveConversation(id: string): void {
  try {
    localStorage.setItem(CONVERSATION_KEY, id);
  } catch {
    // storage unavailable (private mode): the conversation simply is not resumed after a reload
  }
}

export const App: React.FC = () => {
  const [tab, setTab] = useState<Tab>('assistant');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [profile, setProfile] = useState(() => api.getProfile());
  const [command, setCommand] = useState<ChatCommand | null>(null);
  const [showLogin, setShowLogin] = useState(false);
  const [staffLogin, setStaffLogin] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState<string | null>(null);

  const initInFlight = useRef<Promise<void> | null>(null);

  /** Resume the conversation of this browser session; start a new one when asked or when it is gone. */
  const initConversation = useCallback(async (fresh = false) => {
    // React runs mount effects twice in development; one start per moment is enough.
    if (initInFlight.current && !fresh) return initInFlight.current;
    const run = startConversation(fresh);
    initInFlight.current = run;
    try {
      await run;
    } finally {
      if (initInFlight.current === run) initInFlight.current = null;
    }
  }, []);

  const startConversation = async (fresh: boolean) => {
    const saved = fresh ? null : readSavedConversation();
    if (saved) {
      try {
        await api.getConversation(saved);
        setConversationId(saved);
        return;
      } catch {
        // deleted, or it belongs to another identity: fall through to a new one
      }
    }
    try {
      const res = await api.createConversation();
      saveConversation(res.conversation_id);
      setConversationId(res.conversation_id);
    } catch (err) {
      console.error('Error creating conversation:', err);
    }
  };

  useEffect(() => {
    initConversation();
  }, [initConversation]);

  // The API signed us out (expired session): fall back to a guest conversation and say why.
  useEffect(() => {
    const onExpired = () => {
      setProfile(null);
      setTab('assistant');
      setAuthError('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
      setShowLogin(true);
      initConversation(true);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [initConversation]);

  const send = (type: ChatCommand['type']) => {
    setTab('assistant');
    setCommand({ type, nonce: Date.now() });
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    try {
      if (staffLogin) await api.staffLogin(email, password);
      else await api.login(email, password);
      setProfile(api.getProfile());
      setShowLogin(false);
      setPassword('');
      setTab(staffLogin ? 'staff' : 'assistant');
      if (!staffLogin) initConversation(true);
    } catch (err: unknown) {
      setAuthError(err instanceof Error ? err.message : 'Đăng nhập thất bại.');
    }
  };

  const handleLoginButton = () => {
    if (!profile) {
      setShowLogin(true);
      return;
    }
    if (window.confirm('Đăng xuất khỏi tài khoản này?')) {
      api.logout();
      setProfile(null);
      setTab('assistant');
      initConversation(true);
    }
  };

  useEscapeKey(() => setShowLogin(false), showLogin);

  const isStaff = profile?.kind === 'staff';

  return (
    <>
      <div className="ss">
        <header>
          <div className="logo">
            <img src="/images/ui/logo.png" alt="" />
            ShopSupport AI <span className="pl">✦</span>
          </div>
          <nav>
            <button type="button" className={tab === 'assistant' ? 'on' : ''} onClick={() => setTab('assistant')}>
              <ChatIcon />
              <span>Trợ lý AI</span>
            </button>
            <button type="button" onClick={() => send('lookup')}>
              <OrderLookupIcon />
              <span>Tra cứu đơn hàng</span>
            </button>
            <button type="button" onClick={() => send('policies')}>
              <ReceiptIcon />
              <span>Chính sách</span>
            </button>
            <button type="button" onClick={() => send('returns')}>
              <RefreshIcon />
              <span>Đổi trả</span>
            </button>
            <button type="button" onClick={() => send('contact')}>
              <SupportIcon />
              <span>Liên hệ</span>
            </button>
            {isStaff && (
              <button type="button" className={tab === 'staff' ? 'on' : ''} onClick={() => setTab('staff')}>
                <UserIcon />
                <span>Nhân viên</span>
              </button>
            )}
          </nav>
          <div className="hr">
            <button type="button" className="ib" aria-label="Tìm kiếm (chưa hỗ trợ)" aria-disabled="true" title="Chưa hỗ trợ tìm kiếm">
              <SearchIcon />
            </button>
            <button type="button" className="ib" aria-label="Giỏ hàng (chưa hỗ trợ)" aria-disabled="true" title="Chưa hỗ trợ giỏ hàng">
              <CartIcon />
            </button>
            <span style={{ width: 1, height: 24, background: 'var(--bd)', marginLeft: -1.6 }} />
            <button type="button" className="login" onClick={handleLoginButton} title={profile ? 'Đăng xuất' : 'Đăng nhập'}>
              <UserIcon />
              <span>{profile ? profile.label : 'Đăng nhập'}</span>
            </button>
          </div>
        </header>

        {tab === 'staff' && isStaff ? (
          <div className="staff-view">
            <StaffPortal />
          </div>
        ) : conversationId ? (
          <ChatView conversationId={conversationId} isGuest={!profile || isStaff} command={command} />
        ) : (
          <main>
            <section className="left">
              <div className="chat" role="status">
                <p className="empty">Đang khởi tạo phiên làm việc với ShopSupport AI...</p>
              </div>
            </section>
          </main>
        )}
      </div>

      {showLogin &&
        createPortal(
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4" onClick={() => setShowLogin(false)}>
            <div
              className="bg-white rounded-3xl max-w-sm w-full p-6 shadow-2xl border border-brand-100"
              onClick={(e) => e.stopPropagation()}
              role="dialog"
              aria-labelledby="login-title"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-2xl bg-brand-100 text-brand-700 flex items-center justify-center">
                  <LogIn className="w-5 h-5" />
                </div>
                <div>
                  <h3 id="login-title" className="font-bold text-slate-900 text-base">
                    {staffLogin ? 'Đăng nhập nhân viên' : 'Đăng nhập khách hàng'}
                  </h3>
                  <p className="text-xs text-slate-500">Truy cập đầy đủ tính năng và bảo mật đơn hàng</p>
                </div>
              </div>

              {authError && (
                <div className="mb-4 p-3 bg-red-50 text-red-700 text-xs rounded-xl border border-red-200 font-medium" role="alert">
                  {authError}
                </div>
              )}

              <form onSubmit={handleLogin} className="space-y-3.5">
                <div>
                  <label htmlFor="login-email" className="block text-xs font-semibold text-slate-700 mb-1">Email</label>
                  <input
                    id="login-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-brand-500 focus:bg-white focus:outline-none transition"
                    autoComplete="username"
                    required
                  />
                </div>
                <div>
                  <label htmlFor="login-password" className="block text-xs font-semibold text-slate-700 mb-1">Mật khẩu</label>
                  <input
                    id="login-password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-brand-500 focus:bg-white focus:outline-none transition"
                    autoComplete="current-password"
                    required
                  />
                </div>
                <div className="pt-2 flex gap-2">
                  <button type="button" onClick={() => setShowLogin(false)} className="flex-1 py-2.5 text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-xl transition">
                    Hủy
                  </button>
                  <button type="submit" className="flex-1 py-2.5 text-xs font-semibold text-white bg-brand-700 hover:bg-brand-800 rounded-xl shadow-md shadow-brand-200 transition">
                    Đăng nhập
                  </button>
                </div>
              </form>

              <button
                type="button"
                onClick={() => {
                  setStaffLogin(!staffLogin);
                  setAuthError(null);
                }}
                className="mt-4 w-full text-center text-xs text-brand-700 hover:underline"
              >
                {staffLogin ? 'Đăng nhập với tư cách khách hàng' : 'Đăng nhập với tư cách nhân viên'}
              </button>
            </div>
          </div>,
          document.body
        )}
    </>
  );
};
