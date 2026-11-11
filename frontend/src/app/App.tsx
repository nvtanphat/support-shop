import React, { useState, useEffect } from 'react';
import { EnvironmentBanner } from '../components/EnvironmentBanner';
import { ChatView } from '../features/chat/ChatView';
import { StaffPortal } from '../features/staff/StaffPortal';
import { CitationModal } from '../components/CitationModal';
import { GuestOtpModal } from '../features/chat/GuestOtpModal';
import { api } from '../lib/api';
import {
  Sparkles,
  Search,
  ShoppingCart,
  User as UserIcon,
  Bot,
  Package,
  FileText,
  RefreshCw,
  Headphones,
  LogOut,
  LogIn,
  SlidersHorizontal,
} from 'lucide-react';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'assistant' | 'lookup' | 'policy' | 'returns' | 'contact' | 'staff'>('assistant');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [loginEmail, setLoginEmail] = useState('lan.nguyen@example.vn');
  const [loginPassword, setLoginPassword] = useState('SecurePass123!');
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // Global modals triggered from header tabs
  const [selectedClause, setSelectedClause] = useState<string | null>(null);
  const [isOtpModalOpen, setIsOtpModalOpen] = useState(false);

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
      if (activeTab === 'staff') {
        await api.staffLogin(loginEmail, loginPassword);
      } else {
        await api.login(loginEmail, loginPassword);
      }
      setIsLoggedIn(true);
      setShowLoginModal(false);
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

  const handleTabClick = (tab: typeof activeTab) => {
    if (tab === 'lookup') {
      setIsOtpModalOpen(true);
      return;
    }
    if (tab === 'policy') {
      setSelectedClause('POL-RET-ELIG');
      return;
    }
    setActiveTab(tab);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#F6F5FC] text-slate-800 antialiased selection:bg-purple-200">
      <EnvironmentBanner />

      {/* Main Top Header matching ShopSupport AI style */}
      <header className="bg-white/95 backdrop-blur-md border-b border-purple-100/80 sticky top-0 z-40 shadow-xs">
        <div className="max-w-[1520px] mx-auto px-4 lg:px-8 h-18 flex items-center justify-between gap-4">
          
          {/* Left Brand Logo */}
          <div className="flex items-center gap-3 cursor-pointer" onClick={() => setActiveTab('assistant')}>
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center text-white shadow-md shadow-purple-200 overflow-hidden p-1.5">
              <img
                src="/images/brand/shopping-bag-icon.png"
                alt="ShopSupport Logo"
                className="w-full h-full object-contain filter drop-shadow-sm"
              />
            </div>
            <div className="flex items-center gap-1.5">
              <span className="font-extrabold text-slate-900 tracking-tight text-lg">
                ShopSupport AI
              </span>
              <Sparkles className="w-4 h-4 text-purple-600 fill-purple-600 animate-pulse" />
            </div>
          </div>

          {/* Center Navigation Pill Tabs */}
          <nav className="hidden md:flex items-center bg-slate-100/80 p-1.5 rounded-2xl text-xs font-semibold gap-1 border border-slate-200/50">
            <button
              onClick={() => handleTabClick('assistant')}
              className={`px-4 py-2 rounded-xl transition-all flex items-center gap-2 ${
                activeTab === 'assistant'
                  ? 'bg-purple-100/90 text-purple-800 shadow-xs font-bold'
                  : 'text-slate-600 hover:text-purple-700 hover:bg-white/60'
              }`}
            >
              <Bot className="w-4 h-4 text-purple-600" />
              <span>Trợ lý AI</span>
            </button>

            <button
              onClick={() => handleTabClick('lookup')}
              className="px-4 py-2 rounded-xl text-slate-600 hover:text-purple-700 hover:bg-white/60 transition-all flex items-center gap-2"
            >
              <Package className="w-4 h-4 text-slate-500" />
              <span>Tra cứu đơn hàng</span>
            </button>

            <button
              onClick={() => handleTabClick('policy')}
              className="px-4 py-2 rounded-xl text-slate-600 hover:text-purple-700 hover:bg-white/60 transition-all flex items-center gap-2"
            >
              <FileText className="w-4 h-4 text-slate-500" />
              <span>Chính sách</span>
            </button>

            <button
              onClick={() => handleTabClick('returns')}
              className={`px-4 py-2 rounded-xl transition-all flex items-center gap-2 ${
                activeTab === 'returns'
                  ? 'bg-purple-100/90 text-purple-800 shadow-xs font-bold'
                  : 'text-slate-600 hover:text-purple-700 hover:bg-white/60'
              }`}
            >
              <RefreshCw className="w-4 h-4 text-slate-500" />
              <span>Đổi trả</span>
            </button>

            <button
              onClick={() => handleTabClick('contact')}
              className={`px-4 py-2 rounded-xl transition-all flex items-center gap-2 ${
                activeTab === 'contact'
                  ? 'bg-purple-100/90 text-purple-800 shadow-xs font-bold'
                  : 'text-slate-600 hover:text-purple-700 hover:bg-white/60'
              }`}
            >
              <Headphones className="w-4 h-4 text-slate-500" />
              <span>Liên hệ</span>
            </button>

            <div className="h-4 w-[1px] bg-slate-300 mx-1"></div>

            <button
              onClick={() => setActiveTab('staff')}
              className={`px-3.5 py-2 rounded-xl transition-all flex items-center gap-1.5 ${
                activeTab === 'staff'
                  ? 'bg-indigo-600 text-white shadow-xs font-bold'
                  : 'text-indigo-700 bg-indigo-50/80 hover:bg-indigo-100'
              }`}
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>Nhân viên</span>
            </button>
          </nav>

          {/* Right Action Icons & User Profile */}
          <div className="flex items-center gap-3">
            <button
              className="w-10 h-10 rounded-xl hover:bg-purple-50 text-slate-600 hover:text-purple-600 flex items-center justify-center transition"
              title="Tìm kiếm"
            >
              <Search className="w-5 h-5" />
            </button>

            <div className="relative">
              <button
                className="w-10 h-10 rounded-xl hover:bg-purple-50 text-slate-600 hover:text-purple-600 flex items-center justify-center transition"
                title="Giỏ hàng"
              >
                <ShoppingCart className="w-5 h-5" />
              </button>
              <span className="absolute top-1 right-1 w-4 h-4 rounded-full bg-purple-600 text-white text-[10px] font-bold flex items-center justify-center shadow-xs">
                1
              </span>
            </div>

            {isLoggedIn ? (
              <div className="flex items-center gap-2 pl-2 border-l border-slate-200">
                <div className="hidden sm:flex flex-col text-right">
                  <span className="text-xs font-bold text-slate-900 leading-tight">Lan Nguyễn</span>
                  <span className="text-[10px] font-semibold text-purple-600">Khách hàng VIP</span>
                </div>
                <button
                  onClick={handleLogout}
                  className="w-10 h-10 rounded-xl bg-purple-50 hover:bg-red-50 text-purple-700 hover:text-red-600 flex items-center justify-center transition border border-purple-100"
                  title="Đăng xuất"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowLoginModal(true)}
                className="flex items-center gap-2 text-xs font-bold text-slate-700 hover:text-purple-700 bg-white hover:bg-purple-50 px-4 py-2.5 rounded-xl transition border border-purple-200/80 shadow-xs"
              >
                <UserIcon className="w-4 h-4 text-purple-600" />
                <span>Đăng nhập</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Container Area */}
      <main className="flex-1 max-w-[1520px] w-full mx-auto p-4 lg:p-6 flex flex-col min-h-0">
        {activeTab === 'staff' ? (
          <StaffPortal />
        ) : conversationId ? (
          <ChatView
            conversationId={conversationId}
            isGuest={!isLoggedIn}
            quickFilter={activeTab === 'returns' ? 'returns' : activeTab === 'contact' ? 'contact' : undefined}
          />
        ) : (
          <div className="py-24 text-center text-purple-500 text-sm flex flex-col items-center gap-3">
            <div className="w-8 h-8 rounded-full border-2 border-purple-600 border-t-transparent animate-spin"></div>
            <span>Đang khởi tạo phiên làm việc với ShopSupport AI...</span>
          </div>
        )}
      </main>

      {/* Login Modal */}
      {showLoginModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4"
          onClick={() => setShowLoginModal(false)}
        >
          <div
            className="bg-white rounded-3xl max-w-sm w-full p-6 shadow-2xl border border-purple-100 animate-in fade-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-2xl bg-purple-100 text-purple-700 flex items-center justify-center">
                <LogIn className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-bold text-slate-900 text-base">
                  {activeTab === 'staff' ? 'Đăng nhập Nhân viên' : 'Đăng nhập Khách hàng'}
                </h3>
                <p className="text-xs text-slate-500">Truy cập toàn bộ tính năng và bảo mật đơn hàng</p>
              </div>
            </div>

            {authError && (
              <div className="mb-4 p-3 bg-red-50 text-red-700 text-xs rounded-xl border border-red-200 font-medium">
                {authError}
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Email</label>
                <input
                  type="email"
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  className="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-purple-500 focus:bg-white focus:outline-none transition"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Mật khẩu</label>
                <input
                  type="password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  className="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-purple-500 focus:bg-white focus:outline-none transition"
                  required
                />
              </div>

              <div className="pt-2 flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowLoginModal(false)}
                  className="flex-1 py-2.5 text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2.5 text-xs font-semibold text-white bg-purple-600 hover:bg-purple-700 rounded-xl shadow-md shadow-purple-200 transition"
                >
                  Đăng nhập
                </button>
              </div>
            </form>

            <div className="mt-4 pt-3 border-t border-slate-100 text-[11px] text-slate-400 text-center">
              Tài khoản mẫu: <span className="font-mono text-purple-700">lan.nguyen@example.vn</span> / <span className="font-mono text-purple-700">SecurePass123!</span>
            </div>
          </div>
        </div>
      )}

      {/* Policy Citation Modal */}
      <CitationModal
        clauseId={selectedClause}
        onClose={() => setSelectedClause(null)}
      />

      {/* Guest OTP Modal */}
      <GuestOtpModal
        isOpen={isOtpModalOpen}
        onClose={() => setIsOtpModalOpen(false)}
        onVerified={() => {
          initConversation();
        }}
      />
    </div>
  );
};
