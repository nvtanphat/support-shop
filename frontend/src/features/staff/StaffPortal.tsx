import React, { useState, useEffect } from 'react';
import { api } from '../../lib/api';
import { ApprovalRequest, Message, StaffMetrics, StaffReturn, Ticket } from '../../lib/types';
import {
  ShieldCheck,
  Inbox,
  CheckCircle,
  XCircle,
  Clock,
  ArrowRight,
  Headphones,
  Send,
  Loader2,
  AlertCircle,
  Activity,
  Sliders,
} from 'lucide-react';

const ROLE_LABELS: Record<string, string> = {
  agent: 'Chuyên viên Hỗ trợ (Agent)',
  supervisor: 'Trưởng ca (Supervisor)',
  admin: 'Quản trị viên (Admin)',
};

export const StaffPortal: React.FC = () => {
  const role = api.getProfile()?.role ?? 'agent';
  const canSeeMetrics = role === 'supervisor' || role === 'admin'; // the API refuses /staff/metrics to agents
  const canUseSandbox = role === 'admin';
  const [tab, setTab] = useState<'approvals' | 'tickets' | 'returns' | 'metrics' | 'sandbox'>('approvals');
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Approval Decision Dialog state
  const [selectedApproval, setSelectedApproval] = useState<ApprovalRequest | null>(null);
  const [decisionNote, setDecisionNote] = useState('');
  const [decisionLoading, setDecisionLoading] = useState(false);

  // Ticket Chat Takeover state
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [staffMessage, setStaffMessage] = useState('');
  const [takeoverLoading, setTakeoverLoading] = useState(false);

  // Sandbox state
  const [sandboxOrderCode, setSandboxOrderCode] = useState('');
  const [sandboxStatus, setSandboxStatus] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<StaffMetrics | null>(null);
  const [returns, setReturns] = useState<StaffReturn[]>([]);
  const [returnNotice, setReturnNotice] = useState<string | null>(null);

  const runReturnStep = async (step: () => Promise<string>) => {
    setError(null);
    setReturnNotice(null);
    try {
      setReturnNotice(await step());
      setReturns((await api.listStaffReturns()).returns || []);
    } catch (err: any) {
      setError(err.message || 'Thao tác kho thất bại.');
    }
  };
  const [threadMessages, setThreadMessages] = useState<Message[]>([]);

  // The conversation of the selected ticket, refreshed every few seconds so the customer's new messages appear.
  useEffect(() => {
    if (!selectedTicket) {
      setThreadMessages([]);
      return;
    }
    let cancelled = false;
    const load = () =>
      api
        .getConversation(selectedTicket.conversation_id)
        .then((c) => !cancelled && setThreadMessages(c.messages || []))
        .catch(() => undefined);
    load();
    const timer = setInterval(load, 4000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [selectedTicket]);

  const runSandbox = async (action: () => Promise<string>) => {
    setError(null);
    setSandboxStatus(null);
    try {
      setSandboxStatus(await action());
    } catch (err: any) {
      setError(err.message || 'Thao tác sandbox thất bại.');
    }
  };

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      if (tab === 'approvals') {
        const res = await api.listApprovals();
        setApprovals(res.approvals || []);
      } else if (tab === 'tickets') {
        const res = await api.listTickets();
        setTickets(res.tickets || []);
      } else if (tab === 'returns') {
        setReturns((await api.listStaffReturns()).returns || []);
      } else if (tab === 'metrics') {
        setMetrics(await api.staffMetrics());
      }
    } catch (err: any) {
      setError(err.message || 'Không thể tải dữ liệu nhân viên.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [tab]);

  const handleDecision = async (decision: 'approve' | 'reject') => {
    if (!selectedApproval) return;
    if (!decisionNote.trim()) {
      setError('Vui lòng nhập ghi chú bắt buộc cho quyết định duyệt/từ chối.');
      return;
    }

    setDecisionLoading(true);
    setError(null);
    try {
      await api.decideApproval(selectedApproval.id, decision, decisionNote.trim());
      setSelectedApproval(null);
      setDecisionNote('');
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Quyết định duyệt thất bại.');
    } finally {
      setDecisionLoading(false);
    }
  };

  const handleClaimTicket = async (ticket: Ticket) => {
    setTakeoverLoading(true);
    setError(null);
    try {
      await api.claimTicket(ticket.id);
      setSelectedTicket(ticket);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Tiếp nhận phiếu thất bại.');
    } finally {
      setTakeoverLoading(false);
    }
  };

  const handleSendStaffMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTicket || !staffMessage.trim()) return;

    setTakeoverLoading(true);
    try {
      await api.sendStaffMessage(selectedTicket.conversation_id, staffMessage.trim());
      api.getConversation(selectedTicket.conversation_id).then((c) => setThreadMessages(c.messages || [])).catch(() => undefined);
      setStaffMessage('');
    } catch (err: any) {
      setError(err.message || 'Gửi tin nhắn nhân viên thất bại.');
    } finally {
      setTakeoverLoading(false);
    }
  };

  const handleReturnToAi = async () => {
    if (!selectedTicket) return;
    setTakeoverLoading(true);
    try {
      await api.returnToAi(selectedTicket.conversation_id);
      setSelectedTicket(null);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Chuyển trả về cho AI thất bại.');
    } finally {
      setTakeoverLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Bàn làm việc Nhân viên Hỗ trợ</h1>
          <p className="text-sm text-slate-500">
            Cổng phê duyệt, quản lý phiếu hỗ trợ và bảng điều khiển mô phỏng ShopLab.
          </p>
        </div>
        <div className="flex items-center gap-2 bg-indigo-50 border border-indigo-200 text-indigo-900 px-3 py-1.5 rounded-lg text-xs font-semibold">
          <Headphones className="w-4 h-4 text-indigo-700" />
          <span>Vai trò: {ROLE_LABELS[role] ?? ROLE_LABELS.agent}</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 mb-6 space-x-6 text-sm font-medium">
        <button
          onClick={() => setTab('approvals')}
          className={`pb-3 border-b-2 flex items-center gap-2 transition ${
            tab === 'approvals'
              ? 'border-indigo-600 text-indigo-600 font-bold'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <ShieldCheck className="w-4 h-4" />
          <span>Hàng chờ duyệt</span>
          {approvals.length > 0 && (
            <span className="bg-amber-100 text-amber-800 text-xs px-2 py-0.5 rounded-full font-bold">
              {approvals.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setTab('tickets')}
          className={`pb-3 border-b-2 flex items-center gap-2 transition ${
            tab === 'tickets'
              ? 'border-indigo-600 text-indigo-600 font-bold'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <Inbox className="w-4 h-4" />
          <span>Phiếu & Hội thoại tiếp quản</span>
          {tickets.length > 0 && (
            <span className="bg-slate-100 text-slate-700 text-xs px-2 py-0.5 rounded-full font-bold">
              {tickets.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setTab('returns')}
          className={`pb-3 border-b-2 flex items-center gap-2 transition ${
            tab === 'returns'
              ? 'border-indigo-600 text-indigo-600 font-bold'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <Inbox className="w-4 h-4" />
          <span>Kho hàng trả về</span>
        </button>

        {canSeeMetrics && (
        <button
          onClick={() => setTab('metrics')}
          className={`pb-3 border-b-2 flex items-center gap-2 transition ${
            tab === 'metrics'
              ? 'border-indigo-600 text-indigo-600 font-bold'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <Activity className="w-4 h-4" />
          <span>Vận hành & Đo lường</span>
        </button>
        )}

        {canUseSandbox && (
        <button
          onClick={() => setTab('sandbox')}
          className={`pb-3 border-b-2 flex items-center gap-2 transition ${
            tab === 'sandbox'
              ? 'border-indigo-600 text-indigo-600 font-bold'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <Sliders className="w-4 h-4" />
          <span>Bảng mô phỏng</span>
        </button>
        )}
      </div>

      {error && (
        <div className="p-3 mb-6 bg-red-50 text-red-700 text-xs rounded-lg border border-red-200 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Tab 1: Approvals Queue */}
      {tab === 'approvals' && (
        <div className="space-y-4">
          {loading ? (
            <div className="py-12 flex justify-center text-slate-400">
              <Loader2 className="w-6 h-6 animate-spin" />
            </div>
          ) : approvals.length === 0 ? (
            <div className="p-8 text-center bg-white rounded-xl border border-slate-200 text-slate-500">
              <ShieldCheck className="w-8 h-8 mx-auto text-emerald-500 mb-2" />
              <p className="text-sm font-medium">Hiện không có yêu cầu nào đang chờ phê duyệt.</p>
            </div>
          ) : (
            <div className="grid gap-4">
              {approvals.map((req) => (
                <div
                  key={req.id}
                  className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between"
                >
                  <div>
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-xs font-mono font-bold bg-slate-100 text-slate-800 px-2 py-0.5 rounded">
                        Cổng: {req.gate}
                      </span>
                      <span className="text-xs font-semibold text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
                        Vai trò yêu cầu: {req.required_role}
                      </span>
                      <span className="text-xs text-slate-400 flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5" />
                        {new Date(req.requested_at).toLocaleTimeString('vi-VN')}
                      </span>
                    </div>
                    <div className="text-sm font-semibold text-slate-900">
                      {req.subject_type === 'refund' ? 'Hoàn tiền' : req.subject_type === 'return_request' ? 'Yêu cầu trả hàng' : req.subject_type}{' '}
                      {req.refund_code || req.return_code || `#${req.subject_id.slice(0, 8)}`}
                      {req.order_code && <span className="font-normal text-slate-600"> · đơn {req.order_code}</span>}
                      {typeof req.amount === 'number' && (
                        <span className="font-mono text-slate-900"> · {req.amount.toLocaleString('vi-VN')} đ</span>
                      )}
                    </div>
                    {req.note && <div className="text-xs text-slate-500 mt-0.5">{req.note}</div>}
                    {req.subject_type === 'return_request' && req.evidence_count === 0 && (
                      <div className="text-xs text-amber-700 mt-1">Khách chưa tải bằng chứng ảnh/video.</div>
                    )}
                  </div>

                  <button
                    onClick={() => setSelectedApproval(req)}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium flex items-center gap-1.5 transition"
                  >
                    <span>Xem xét & Duyệt</span>
                    <ArrowRight className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Tickets & Chat Takeover */}
      {tab === 'tickets' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Ticket list */}
          <div className="space-y-3">
            <h3 className="text-sm font-bold text-slate-800 mb-2">Danh sách phiếu hỗ trợ</h3>
            {tickets.map((t) => (
              <div
                key={t.id}
                onClick={() => setSelectedTicket(t)}
                className={`p-4 rounded-xl border cursor-pointer transition ${
                  selectedTicket?.id === t.id
                    ? 'border-indigo-600 bg-indigo-50/50'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs font-mono font-bold text-indigo-700">{t.code}</span>
                  <span className="text-[10px] font-semibold bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded">
                    {t.priority}
                  </span>
                </div>
                <div className="text-xs font-medium text-slate-800 mb-1">{t.reason_code}</div>
                <p className="text-xs text-slate-500 line-clamp-2">{t.summary}</p>
                {!t.assigned_to && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleClaimTicket(t);
                    }}
                    className="mt-2 text-xs text-indigo-600 font-bold hover:underline"
                  >
                    Tiếp nhận phiếu này →
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* Chat Takeover Workspace */}
          <div className="md:col-span-2 bg-white rounded-xl border border-slate-200 p-5 flex flex-col h-[500px]">
            {selectedTicket ? (
              <>
                <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
                  <div>
                    <h4 className="text-sm font-bold text-slate-900">
                      Phiếu: {selectedTicket.code}
                    </h4>
                    <p className="text-xs text-slate-500">{selectedTicket.summary}</p>
                  </div>
                  <button
                    onClick={handleReturnToAi}
                    className="text-xs bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 font-semibold px-3 py-1.5 rounded-lg transition"
                  >
                    Trả hội thoại về cho AI
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto p-3 bg-slate-50 rounded-lg text-xs text-slate-700 mb-4 border border-slate-200 space-y-2">
                  {threadMessages.length === 0 ? (
                    <div className="text-center text-slate-400 py-6">Chưa có tin nhắn trong cuộc trò chuyện này.</div>
                  ) : (
                    threadMessages.map((m) => (
                      <div key={m.id} className={m.role === 'customer' ? 'text-left' : 'text-right'}>
                        <span className="block text-[10px] font-semibold text-slate-400">
                          {m.role === 'customer' ? 'Khách hàng' : m.role === 'staff' ? 'Nhân viên' : 'Trợ lý AI'}
                        </span>
                        <span
                          className={`inline-block px-3 py-1.5 rounded-lg whitespace-pre-wrap ${
                            m.role === 'customer' ? 'bg-white border border-slate-200' : m.role === 'staff' ? 'bg-indigo-600 text-white' : 'bg-slate-200'
                          }`}
                        >
                          {m.content}
                        </span>
                      </div>
                    ))
                  )}
                </div>

                <form onSubmit={handleSendStaffMessage} className="flex gap-2">
                  <input
                    type="text"
                    value={staffMessage}
                    onChange={(e) => setStaffMessage(e.target.value)}
                    placeholder="Nhập phản hồi trực tiếp tới khách hàng..."
                    className="flex-1 px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={takeoverLoading || !staffMessage.trim()}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium flex items-center gap-1.5 disabled:opacity-50"
                  >
                    <Send className="w-4 h-4" />
                    <span>Gửi</span>
                  </button>
                </form>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-400 text-sm">
                <Inbox className="w-10 h-10 mb-2 stroke-1" />
                <span>Chọn một phiếu hỗ trợ để xem và tiếp quản cuộc trò chuyện.</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Returns in the warehouse workflow: receive the parcel, then record the inspection */}
      {tab === 'returns' && (
        <div className="space-y-3">
          {returnNotice && (
            <div className="p-3 bg-emerald-50 text-emerald-800 text-xs rounded-lg border border-emerald-200">{returnNotice}</div>
          )}
          {returns.length === 0 ? (
            <div className="text-sm text-slate-400">Không có yêu cầu trả hàng nào đang chờ kho.</div>
          ) : (
            returns.map((r) => (
              <div key={r.code} className="bg-white p-4 rounded-xl border border-slate-200 flex items-center justify-between gap-4">
                <div className="text-sm">
                  <div className="font-semibold text-slate-900">
                    {r.code} <span className="font-normal text-slate-600">· đơn {r.order_code}</span>
                  </div>
                  <div className="text-xs text-slate-500">
                    {r.status} · {r.reason_code} · {r.evidence_count} bằng chứng
                  </div>
                </div>
                {r.status === 'awaiting_return' && (
                  <button
                    type="button"
                    className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-medium rounded-lg"
                    onClick={() => runReturnStep(async () => `${(await api.receiveReturn(r.code)).code}: đã nhận hàng về kho.`)}
                  >
                    Xác nhận đã nhận hàng
                  </button>
                )}
                {r.status === 'received' && (
                  <button
                    type="button"
                    className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium rounded-lg"
                    onClick={() =>
                      runReturnStep(async () => {
                        const res = await api.inspectReturn(r.code, 'Kiểm hàng đạt');
                        return `${res.message} (${res.refund_code}: ${res.refund_amount.toLocaleString('vi-VN')} đ)`;
                      })
                    }
                  >
                    Kiểm hàng đạt
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab 3: Metrics, computed by the server from the database */}
      {tab === 'metrics' && metrics && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {(
            [
              ['Phê duyệt theo trạng thái', metrics.approvals_by_status],
              ['Phiếu hỗ trợ theo trạng thái', metrics.tickets_by_status],
              ['Hoàn tiền theo trạng thái', metrics.refunds_by_status],
              ['Hàng đợi outbox theo trạng thái', metrics.outbox_by_status],
            ] as [string, Record<string, number>][]
          ).map(([title, counts]) => (
            <div key={title} className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">{title}</div>
              {Object.keys(counts).length === 0 ? (
                <div className="text-xs text-slate-400">Chưa có dữ liệu</div>
              ) : (
                Object.entries(counts).map(([status, count]) => (
                  <div key={status} className="flex justify-between text-sm text-slate-700">
                    <span>{status}</span>
                    <span className="font-mono font-bold text-slate-900">{count}</span>
                  </div>
                ))
              )}
            </div>
          ))}
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Đánh giá của khách</div>
            <div className="text-2xl font-bold text-slate-900">
              {metrics.feedback.average_rating === null ? 'Chưa có' : `${metrics.feedback.average_rating} / 5`}
            </div>
            <div className="text-xs text-slate-400 mt-1">{metrics.feedback.count} lượt đánh giá</div>
          </div>
        </div>
      )}

      {/* Tab 4: Sandbox Controls */}
      {tab === 'sandbox' && (
        <div className="bg-white p-6 rounded-xl border border-slate-200 max-w-xl">
          <h3 className="text-base font-bold text-slate-900 mb-1">
            Bảng điều khiển Mô phỏng Sandbox
          </h3>
          <p className="text-xs text-slate-500 mb-4">
            Dành cho kiểm thử tích hợp: cập nhật trạng thái vận đơn, kích hoạt thanh toán lỗi.
          </p>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Mã vận đơn:
              </label>
              <input
                type="text"
                placeholder="Mã vận đơn cần đẩy bước"
                value={sandboxOrderCode}
                onChange={(e) => setSandboxOrderCode(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                disabled={!sandboxOrderCode.trim()}
                onClick={() =>
                  runSandbox(async () => {
                    const res = await api.sandboxAdvanceShipment(sandboxOrderCode.trim());
                    return `Vận đơn ${res.tracking_code} đã chuyển sang: ${res.status}`;
                  })
                }
                className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg"
              >
                Đẩy vận đơn một bước
              </button>
              <button
                type="button"
                onClick={() =>
                  runSandbox(async () => {
                    await api.sandboxFailNextPayment();
                    return 'Đã tiêm lỗi: lượt hoàn tiền kế tiếp của cổng giả lập sẽ thất bại một lần';
                  })
                }
                className="px-3 py-2 bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 text-xs font-medium rounded-lg"
              >
                Tiêm lỗi thanh toán
              </button>
            </div>

            {sandboxStatus && (
              <div className="p-3 bg-emerald-50 text-emerald-800 text-xs rounded-lg border border-emerald-200">
                {sandboxStatus}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Decision Dialog Modal */}
      {selectedApproval && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 text-slate-850 relative">
            <h3 className="text-lg font-bold text-slate-900 mb-2">
              Phê duyệt yêu cầu: {selectedApproval.gate}
            </h3>
            <p className="text-xs text-slate-500 mb-4 font-mono">
              Subject ID: {selectedApproval.subject_id}
            </p>

            <div className="mb-4">
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Ghi chú quyết định (bắt buộc):
              </label>
              <textarea
                value={decisionNote}
                onChange={(e) => setDecisionNote(e.target.value)}
                placeholder="Nhập lý do duyệt hoặc lý do từ chối..."
                rows={3}
                className="w-full p-3 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>

            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setSelectedApproval(null)}
                className="px-4 py-2 border border-slate-300 hover:bg-slate-50 rounded-lg text-sm font-medium text-slate-700"
              >
                Đóng
              </button>
              <button
                type="button"
                disabled={decisionLoading || !decisionNote.trim()}
                onClick={() => handleDecision('reject')}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium flex items-center gap-1.5 disabled:opacity-50"
              >
                <XCircle className="w-4 h-4" />
                <span>Từ chối</span>
              </button>
              <button
                type="button"
                disabled={decisionLoading || !decisionNote.trim()}
                onClick={() => handleDecision('approve')}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium flex items-center gap-1.5 disabled:opacity-50"
              >
                <CheckCircle className="w-4 h-4" />
                <span>Chấp thuận</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
