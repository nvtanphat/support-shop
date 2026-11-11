import React, { useState } from 'react';
import { api } from '../../lib/api';
import { X, KeyRound, Phone, Package, AlertCircle, Loader2, ExternalLink } from 'lucide-react';

interface GuestOtpModalProps {
  isOpen: boolean;
  onClose: () => void;
  onVerified: () => void;
}

export const GuestOtpModal: React.FC<GuestOtpModalProps> = ({
  isOpen,
  onClose,
  onVerified,
}) => {
  const [step, setStep] = useState<'request' | 'otp'>('request');
  const [orderCode, setOrderCode] = useState('');
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [verificationId, setVerificationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

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
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 text-slate-850 relative animate-in fade-in zoom-in-95"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 rounded-lg p-1"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2.5 text-emerald-700 font-bold mb-2">
          <KeyRound className="w-5 h-5" />
          <h3 className="text-lg text-slate-900">
            {step === 'request' ? 'Xác minh đơn hàng' : 'Nhập mã xác thực OTP'}
          </h3>
        </div>

        <p className="text-xs text-slate-600 mb-4">
          {step === 'request'
            ? 'Để bảo mật thông tin, khách vãng lai vui lòng cung cấp mã đơn và số điện thoại đặt hàng để nhận mã OTP.'
            : 'Mã OTP 6 số đã được gửi qua SMS tới số điện thoại đặt hàng.'}
        </p>

        {error && (
          <div className="p-3 mb-4 bg-red-50 text-red-700 text-xs rounded-lg border border-red-200 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {infoMessage && (
          <div className="p-3 mb-4 bg-emerald-50 text-emerald-800 text-xs rounded-lg border border-emerald-200">
            {infoMessage}
          </div>
        )}

        {step === 'request' ? (
          <form onSubmit={handleRequestOtp} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Mã đơn hàng:
              </label>
              <div className="relative">
                <Package className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="text"
                  placeholder="Ví dụ: SL-900001"
                  value={orderCode}
                  onChange={(e) => setOrderCode(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:outline-none"
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
                  placeholder="0901234567"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Nhận mã OTP'}
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
                className="w-full text-center tracking-widest text-lg font-mono py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                required
              />
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-xs text-slate-500 flex items-center justify-between">
              <span>Hộp thư SMS mô phỏng:</span>
              <a
                href="/sandbox/sms"
                target="_blank"
                rel="noreferrer"
                className="text-emerald-700 font-medium hover:underline flex items-center gap-1"
              >
                <span>Xem SMS</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setStep('request')}
                className="px-3 py-2 text-xs text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Quay lại
              </button>
              <button
                type="submit"
                disabled={loading || otp.length < 6}
                className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition disabled:opacity-50"
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
