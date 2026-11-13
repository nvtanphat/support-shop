import React, { useState, useEffect } from 'react';
import { PendingAction } from '../../lib/types';
import { api } from '../../lib/api';
import { CheckCircle2, XCircle, Clock, AlertCircle, ArrowRight, ShieldAlert } from 'lucide-react';

interface ActionCardProps {
  action: PendingAction;
  onActionUpdated: (updated: PendingAction) => void;
  onOpenEvidenceUpload?: (returnCode: string) => void;
}

export const ActionCard: React.FC<ActionCardProps> = ({
  action,
  onActionUpdated,
  onOpenEvidenceUpload,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timeLeft, setTimeLeft] = useState<string>('');

  // Countdown timer
  useEffect(() => {
    if (action.status !== 'proposed') return;

    const updateTimer = () => {
      const diff = new Date(action.expires_at).getTime() - Date.now();
      if (diff <= 0) {
        setTimeLeft('Đã hết hạn');
        onActionUpdated({ ...action, status: 'expired' });
      } else {
        const mins = Math.floor(diff / 60000);
        const secs = Math.floor((diff % 60000) / 1000);
        setTimeLeft(`${mins}:${secs < 10 ? '0' : ''}${secs}`);
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [action.expires_at, action.status]);

  const handleConfirm = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.confirmAction(action.id, action.payload_hash);
      // Whatever the outcome (done, waiting for staff, waiting for evidence), the proposal itself is settled.
      const { result: nested, ...flat } = res;
      const updated: PendingAction = {
        ...action,
        status: 'confirmed',
        result: nested ?? flat,
      };
      onActionUpdated(updated);
    } catch (err: any) {
      setError(err.message || 'Xác nhận thất bại.');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.cancelAction(action.id);
      onActionUpdated({ ...action, status: 'cancelled' });
    } catch (err: any) {
      setError(err.message || 'Hủy thất bại.');
    } finally {
      setLoading(false);
    }
  };

  const isProposed = action.status === 'proposed';
  const isConfirmed = action.status === 'confirmed' || action.status === 'executed';
  const isCancelled = action.status === 'cancelled';
  const isExpired = action.status === 'expired';

  return (
    <div className="bg-white border-2 border-purple-400/90 rounded-2xl p-5 my-3 shadow-md transition-all">
      <div className="flex items-center justify-between border-b border-purple-100 pb-3 mb-3">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-purple-700 animate-pulse"></span>
          <h4 className="font-bold text-slate-900 text-sm md:text-base">
            {action.preview.title || 'Đề xuất xử lý'}
          </h4>
        </div>
        {isProposed && (
          <div className="flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 px-2.5 py-1 rounded-lg border border-amber-200">
            <Clock className="w-3.5 h-3.5" />
            <span>Hết hạn: {timeLeft}</span>
          </div>
        )}
      </div>

      <p className="text-sm text-slate-700 mb-3">{action.preview.description}</p>

      {/* Breakdown Details & Estimated Refund */}
      {(action.preview.breakdown || action.preview.estimated_refund_vnd !== undefined) && (
        <div className="bg-purple-50/50 rounded-xl p-3 text-xs mb-3 space-y-1.5 border border-purple-100">
          {action.preview.breakdown && (
            <>
              <div className="font-semibold text-slate-800 mb-1">Chi tiết giải trình số tiền:</div>
              {Object.entries(action.preview.breakdown).map(([k, v]) => (
                <div key={k} className="flex justify-between text-slate-600">
                  <span>{k}:</span>
                  <span className="font-mono font-medium text-slate-900">
                    {typeof v === 'number' ? `${v.toLocaleString('vi-VN')} đ` : String(v)}
                  </span>
                </div>
              ))}
            </>
          )}
          {action.preview.estimated_refund_vnd !== undefined && (
            <div className="flex justify-between font-bold text-purple-900 pt-1.5 border-t border-purple-100 text-sm">
              <span>Khoản hoàn ước tính:</span>
              <span className="font-mono text-purple-700 text-base">
                {action.preview.estimated_refund_vnd.toLocaleString('vi-VN')} đ
              </span>
            </div>
          )}
        </div>
      )}

      {action.preview.refund_explanation && (
        <p className="text-xs text-slate-600 mb-3">{action.preview.refund_explanation}</p>
      )}

      {/* Evidence & Approval Notices */}
      {action.preview.requires_evidence && isProposed && (
        <div className="bg-purple-50 text-purple-800 text-xs p-2.5 rounded-xl mb-3 flex items-start gap-2 border border-purple-200">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5 text-purple-700" />
          <span>
            Yêu cầu cung cấp bằng chứng hình ảnh/video sản phẩm sau khi bấm xác nhận.
          </span>
        </div>
      )}

      {action.preview.requires_approval && (
        <div className="bg-indigo-50 text-indigo-800 text-xs p-2.5 rounded-xl mb-3 flex items-start gap-2 border border-indigo-200">
          <ShieldAlert className="w-4 h-4 flex-shrink-0 mt-0.5 text-indigo-600" />
          <span>Yêu cầu này sẽ được nhân viên duyệt trước khi thực thi giải ngân.</span>
        </div>
      )}

      {error && (
        <div className="p-2.5 mb-3 bg-red-50 text-red-700 text-xs rounded-xl border border-red-200 flex items-center gap-1.5">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Actions / Status Tracker */}
      {isProposed && (
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="flex-1 bg-purple-700 hover:bg-purple-700 text-white font-semibold py-2.5 px-4 rounded-xl text-sm flex items-center justify-center gap-2 transition disabled:opacity-50 shadow-md shadow-purple-200"
          >
            <CheckCircle2 className="w-4 h-4" />
            <span>Xác nhận</span>
          </button>
          <button
            onClick={handleCancel}
            disabled={loading}
            className="px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium rounded-xl text-sm flex items-center justify-center gap-1.5 transition disabled:opacity-50"
          >
            <XCircle className="w-4 h-4 text-slate-500" />
            <span>Hủy</span>
          </button>
        </div>
      )}

      {isConfirmed && (
        <div className="pt-2 border-t border-slate-100 flex flex-col gap-2">
          <div className="flex items-center gap-2 text-emerald-700 text-sm font-semibold">
            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
            <span>Đã xác nhận thành công!</span>
          </div>
          {action.result?.message && <div className="text-xs text-slate-600">{action.result.message}</div>}
          {action.result?.return_code && (
            <div className="text-xs text-slate-600">
              Mã yêu cầu trả hàng: <strong className="font-mono text-slate-900">{action.result.return_code}</strong>
            </div>
          )}
          {action.result?.requires_evidence && onOpenEvidenceUpload && action.result.return_code && (
            <button
              onClick={() => onOpenEvidenceUpload(action.result?.return_code)}
              className="mt-2 text-xs bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-3 rounded-lg flex items-center justify-center gap-1.5 transition w-fit"
            >
              <span>Tải lên bằng chứng ảnh/video</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      )}

      {isCancelled && (
        <div className="pt-2 border-t border-slate-100 flex items-center gap-2 text-slate-500 text-sm">
          <XCircle className="w-4 h-4" />
          <span>Đề xuất đã bị hủy.</span>
        </div>
      )}

      {isExpired && (
        <div className="pt-2 border-t border-slate-100 flex items-center gap-2 text-amber-600 text-sm">
          <Clock className="w-4 h-4" />
          <span>Đề xuất đã hết hạn hiệu lực.</span>
        </div>
      )}
    </div>
  );
};
