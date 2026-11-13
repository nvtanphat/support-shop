import React from 'react';
import type { PolicySummary } from '../../../lib/types';
import { canRequestReturn, formatDate, formatVnd, paymentLabel, statusLabel } from '../../../lib/orderView';
import { useOrder } from '../../../lib/useOrder';
import {
  CalendarIcon,
  CardIcon,
  CheckIcon,
  ChevronIcon,
  DocIcon,
  OrderPanelIcon,
  PackageIcon,
  PolicyBookIcon,
  RefreshIcon,
  TruckIcon,
} from '../../../components/icons';

export interface PolicyListState {
  status: 'loading' | 'ready' | 'error';
  policies: PolicySummary[];
  message?: string;
}

interface SidebarProps {
  orderCode: string | null;
  policies: PolicyListState;
  /** Clause ids the assistant cited in this conversation, newest first. */
  citedClauseIds: string[];
  isGuest: boolean;
  onQuickPrompt: (prompt: string) => void;
  onSelectClause: (clauseId: string) => void;
  onOpenOtp: () => void;
}

const RELATED_FALLBACK_TOPIC = 'return';
const MAX_RELATED = 3;

/** Related policies: what the assistant cited so far, else the return rules (the usual next question). */
export function relatedPolicies(policies: PolicySummary[], citedIds: string[]): PolicySummary[] {
  const cited = citedIds.map((id) => policies.find((p) => p.clause_id === id)).filter((p): p is PolicySummary => !!p);
  const picked = cited.length ? cited : policies.filter((p) => p.topic === RELATED_FALLBACK_TOPIC);
  return picked.slice(0, MAX_RELATED);
}

const OrderPanel: React.FC<Pick<SidebarProps, 'orderCode' | 'isGuest' | 'onQuickPrompt' | 'onOpenOtp'>> = ({
  orderCode,
  isGuest,
  onQuickPrompt,
  onOpenOtp,
}) => {
  const state = useOrder(orderCode);

  if (!orderCode || state.status === 'idle') {
    return (
      <div className="panel">
        <div className="ph">
          <OrderPanelIcon />
          <h3>Đơn hàng</h3>
        </div>
        <p className="empty">
          Chưa có đơn hàng nào được chọn. Hãy nhập <b>mã đơn</b> (dạng SL-XXXXXX) trong cuộc trò chuyện để xem chi tiết tại đây.
        </p>
      </div>
    );
  }

  if (state.status === 'loading') {
    return (
      <div className="panel">
        <div className="ph">
          <OrderPanelIcon />
          <h3>Đơn hàng {orderCode}</h3>
        </div>
        <p className="empty" role="status">Đang tải thông tin đơn hàng...</p>
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="panel">
        <div className="ph">
          <OrderPanelIcon />
          <h3>Đơn hàng {orderCode}</h3>
        </div>
        <p className="empty" role="alert">
          {state.message}
          {isGuest && ' Quý khách chưa đăng nhập: hãy xác thực OTP bằng số điện thoại đặt hàng để xem đơn.'}
        </p>
        {isGuest && (
          <button type="button" className="req" onClick={onOpenOtp}>
            Xác thực OTP tra cứu
          </button>
        )}
      </div>
    );
  }

  const { order } = state;
  const delivered = order.status === 'delivered' || order.status === 'completed';
  return (
    <div className="panel">
      <div className="ph">
        <OrderPanelIcon />
        <h3>Đơn hàng {order.order_code}</h3>
        <span className={`ok${delivered ? '' : ' muted'}`}>
          {delivered && <CheckIcon />}
          {statusLabel(order.status)}
        </span>
      </div>
      {order.items.map((item) => (
        <div className="prod" key={item.item_id}>
          <div className="im">
            <PackageIcon />
          </div>
          <div className="n">{item.product_name}</div>
          <span className="q">x{item.qty}</span>
          <span className="pr">{formatVnd(item.unit_price * item.qty)}</span>
        </div>
      ))}
      {order.placed_at && (
        <div className="row">
          <CalendarIcon />
          <span className="k">Ngày đặt hàng</span>
          <span className="v">{formatDate(order.placed_at)}</span>
        </div>
      )}
      {order.delivered_at && (
        <div className="row">
          <TruckIcon />
          <span className="k">Ngày giao hàng</span>
          <span className="v">{formatDate(order.delivered_at)}</span>
        </div>
      )}
      <div className="row">
        <CardIcon />
        <span className="k">Phương thức thanh toán</span>
        <span className="v">{paymentLabel(order.payment_method)}</span>
      </div>
      {canRequestReturn(order) && (
        <button type="button" className="req" onClick={() => onQuickPrompt(`Tạo yêu cầu đổi trả cho đơn ${order.order_code}`)}>
          <RefreshIcon />
          Yêu cầu đổi trả
        </button>
      )}
    </div>
  );
};

export const OrderContextSidebar: React.FC<SidebarProps> = (props) => {
  const related = relatedPolicies(props.policies.policies, props.citedClauseIds);
  return (
    <aside>
      <OrderPanel {...props} />
      <div className="panel">
        <div className="ph sep">
          <PolicyBookIcon className="pbook" />
          <h3>Chính sách liên quan</h3>
        </div>
        {props.policies.status === 'loading' && <p className="empty" role="status">Đang tải chính sách...</p>}
        {props.policies.status === 'error' && <p className="empty" role="alert">{props.policies.message}</p>}
        {props.policies.status === 'ready' && related.length === 0 && (
          <p className="empty">Chưa có điều khoản chính sách nào đang có hiệu lực.</p>
        )}
        {related.map((policy) => (
          <div
            className="pol"
            key={policy.clause_id}
            role="button"
            tabIndex={0}
            onClick={() => props.onSelectClause(policy.clause_id)}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && props.onSelectClause(policy.clause_id)}
          >
            <span className="d">
              <DocIcon />
            </span>
            <span>{policy.title}</span>
            <ChevronIcon />
          </div>
        ))}
      </div>
    </aside>
  );
};
