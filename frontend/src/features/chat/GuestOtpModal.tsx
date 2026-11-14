import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { X, KeyRound, Phone, Package, AlertCircle, Loader2, Sparkles } from 'lucide-react';
import { useEscapeKey } from '../../lib/useEscapeKey';

interface GuestOtpModalProps {
  isOpen: boolean;
  onClose: () => void;
  onVerified: () => void;
  /** Order code worth suggesting (the one under discussion); the customer can overwrite it. */
  defaultOrderCode?: string | null;
}

export const GuestOtpModal: React.FC<GuestOtpModalProps> = ({
  isOpen,
  onClose,
  onVerified,
  defaultOrderCode,
}) => {
  useEscapeKey(onClose);
  const [step, setStep] = useState<'request' | 'otp'>('request');
  const [orderCode, setOrderCode] = useState(defaultOrderCode ?? '');
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [verificationId, setVerificationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  // Suggest the order under discussion each time the dialog opens with an empty field.
  useEffect(() => {
    if (isOpen && !orderCode && defaultOrderCode) setOrderCode(defaultOrderCode);
  }, [isOpen, defaultOrderCode, orderCode]);

  if (!isOpen) return null;

  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orderCode || !phone) {
      setError('Vui lòng nhập đầy đủ mã đơn hàng và số điện thoại.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await api.requestGuestVerification(orderCode.trim(), phone.trim());
      setVerificationId(res.verification_id);
      setInfoMessage(res.message);
      if (res.simulated_otp) {
        setOtp(res.simulated_otp);
      }
      setStep('otp');
    } catch (err: any) {
      setError(err.message || 'Gửi yêu cầu OTP thất bại.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otp || !verificationId) {
      setError('Vui lòng nhập mã OTP 6 chữ số.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await api.verifyGuestOtp(verificationId, otp.trim());
      onVerified();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Xác minh OTP thất bại.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-3xl shadow-2xl max-w-md w-full p-6 text-slate-800 relative border border-brand-100 animate-in fade-in zoom-in-95"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
      >
        <button
          onClick={onClose}
          className="absolute top-5 right-5 text-slate-400 hover:text-slate-600 rounded-xl p-1 hover:bg-slate-100 transition"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-2xl bg-brand-100 text-brand-700 flex items-center justify-center">
            <KeyRound className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-900">
              {step === 'request' ? 'Xác minh Đơn hàng Vãng lai' : 'Nhập mã xác thực OTP'}
            </h3>
            <p className="text-xs text-slate-500">Tra cứu an toàn bảo vệ quyền riêng tư</p>
          </div>
        </div>

        <p className="text-xs text-slate-600 my-3 leading-relaxed">
          {step === 'request'
            ? 'Để bảo mật thông tin đơn hàng theo tiêu chuẩn TMĐT 2026, vui lòng nhập mã đơn và số điện thoại đặt hàng để nhận mã OTP xác thực.'
            : 'Mã OTP 6 số đã được gửi qua SMS tới số điện thoại đặt hàng.'}
        </p>

        {error && (
          <div className="p-3 mb-4 bg-red-50 text-red-700 text-xs rounded-xl border border-red-200 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {infoMessage && (
          <div className="p-3 mb-4 bg-brand-50 text-brand-800 text-xs rounded-xl border border-brand-200">
            {infoMessage}
          </div>
        )}

        {step === 'request' ? (
          <form onSubmit={handleRequestOtp} className="space-y-3.5">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Mã đơn hàng:
              </label>
              <div className="relative">
                <Package className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="text"
                  placeholder="Ví dụ: SL-XXXXXX"
                  value={orderCode}
                  onChange={(e) => setOrderCode(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-brand-500 focus:bg-white focus:outline-none transition uppercase font-mono"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Số điện thoại đặt hàng:
              </label>
              <div className="relative">
                <Phone className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="tel"
                  placeholder="Số điện thoại dùng khi đặt hàng"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-brand-500 focus:bg-white focus:outline-none transition"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Gửi mã OTP qua SMS'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerifyOtp} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Mã OTP (6 số):
              </label>
              <input
                type="text"
                maxLength={6}
                placeholder="123456"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                className="w-full text-center tracking-widest text-xl font-mono py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-brand-500 focus:bg-white focus:outline-none transition"
                required
              />
            </div>

            {otp && (
              <div className="bg-brand-50 border border-brand-100 rounded-xl p-2.5 text-xs text-brand-700 flex items-center gap-1.5">
                <Sparkles className="w-4 h-4 text-brand-700 flex-shrink-0" />
                <span>Mã OTP mô phỏng đã được nạp tự động: <strong>{otp}</strong></span>
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={() => setStep('request')}
                className="px-4 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                Quay lại
              </button>
              <button
                type="submit"
                disabled={loading || otp.length < 6}
                className="flex-1 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition disabled:opacity-50"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Xác thực & Xem đơn'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
