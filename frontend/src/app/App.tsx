import React, { useState, useEffect } from 'react';
import { EnvironmentBanner } from '../components/EnvironmentBanner';
import { ChatView } from '../features/chat/ChatView';
import { StaffPortal } from '../features/staff/StaffPortal';
import { api } from '../lib/api';
import { User, Headphones, LogIn, LogOut, MessageSquarePlus } from 'lucide-react';

export const App: React.FC = () => {
  const [view, setView] = useState<'customer' | 'staff'>('customer');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [loginEmail, setLoginEmail] = useState('lan.nguyen@example.vn');
  const [loginPassword, setLoginPassword] = useState('SecurePass123!');
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // Initialize or create new conversation
  const initConversation = async () => {
    try {
      const res = await api.createConversation();
      setConversationId(res.conversation_id);
    } catch (err) {
      console.error('Error creating conversation:', err);
    }
  };

  useEffect(() => {
    initConversation();
    const token = api.getToken();
    if (token) setIsLoggedIn(true);
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    try {
      if (view === 'staff') {
        await api.staffLogin(loginEmail, loginPassword);
      } else {
        await api.login(loginEmail, loginPassword);
      }
      setIsLoggedIn(true);
      setShowLoginModal(false);
      // Re-create or reload conversation as authenticated customer
      initConversation();
    } catch (err: any) {
      setAuthError(err.message || 'Đăng nhập thất bại.');
    }
  };

  const handleLogout = () => {
    api.logout();
    setIsLoggedIn(false);
    initConversation();
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-850">
      <EnvironmentBanner />

      {/* Main Navigation Bar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-xs">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center text-white font-black text-lg">
                S
              </div>
              <div>
                <span className="font-extrabold text-slate-900 tracking-tight text-base">
                  ShopLab
                </span>
                <span className="text-xs text-slate-400 font-medium ml-1.5 hidden sm:inline">
                  AI Support Hub
                </span>
              </div>
            </div>

            {/* View Switcher */}
            <nav className="flex bg-slate-100 p-1 rounded-xl text-xs font-semibold">
              <button
                onClick={() => setView('customer')}
                className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 ${
                  view === 'customer'
                    ? 'bg-white text-emerald-700 shadow-xs font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <User className="w-3.5 h-3.5" />
                <span>Khách hàng</span>
              </button>

              <button
                onClick={() => setView('staff')}
                className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 ${
                  view === 'staff'
                    ? 'bg-white text-indigo-700 shadow-xs font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Headphones className="w-3.5 h-3.5" />
                <span>Nhân viên</span>
              </button>
            </nav>
          </div>

          {/* Right Header Actions */}
          <div className="flex items-center gap-3">
            {view === 'customer' && (
              <button
                onClick={initConversation}
                className="hidden sm:flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg transition"
                title="Bắt đầu hội thoại mới"
              >
                <MessageSquarePlus className="w-4 h-4 text-emerald-600" />
                <span>Hội thoại mới</span>
              </button>
            )}

            {isLoggedIn ? (
              <button
                onClick={handleLogout}
                className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-red-600 border border-slate-200 px-3 py-1.5 rounded-lg transition"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Đăng xuất</span>
              </button>
            ) : (
              <button
                onClick={() => setShowLoginModal(true)}
                className="flex items-center gap-1.5 text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-white px-3.5 py-1.5 rounded-lg transition shadow-xs"
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>{view === 'staff' ? 'Đăng nhập Nhân viên' : 'Đăng nhập Khách'}</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main View Area */}
      <main className="flex-1 max-w-6xl w-full mx-auto p-4 md:py-6">
        {view === 'customer' ? (
          conversationId ? (
            <ChatView conversationId={conversationId} isGuest={!isLoggedIn} />
          ) : (
            <div className="py-20 text-center text-slate-400 text-sm">
              Đang khởi tạo kênh trò chuyện...
            </div>
          )
        ) : (
          <StaffPortal />
        )}
      </main>

      {/* Login Modal */}
      {showLoginModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4"
          onClick={() => setShowLoginModal(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6 text-slate-850 relative animate-in fade-in zoom-in-95"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-bold text-slate-900 mb-1">
              {view === 'staff' ? 'Đăng nhập Nhân viên Hỗ trợ' : 'Đăng nhập Khách hàng'}
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              {view === 'staff'
                ? 'Sử dụng tài khoản nhân viên (agent@shoplab.vn) để quản lý hàng chờ.'
                : 'Đăng nhập để tra cứu danh sách đơn và quyền tự phục vụ.'}
            </p>

            {authError && (
              <div className="p-3 mb-4 bg-red-50 text-red-700 text-xs rounded-lg border border-red-200">
                {authError}
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Email:</label>
                <input
                  type="email"
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Mật khẩu:</label>
                <input
                  type="password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                  required
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowLoginModal(false)}
                  className="px-3 py-2 text-xs text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg transition"
                >
                  Đăng nhập
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
