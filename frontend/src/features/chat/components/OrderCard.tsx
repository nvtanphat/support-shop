import React from 'react';
import type { OrderDetail } from '../../../lib/types';
import { canRequestReturn, formatDate, formatVnd, statusLabel, timelineFor } from '../../../lib/orderView';
import { CheckIcon, DocIcon, PackageIcon, RefreshIcon } from '../../../components/icons';

interface OrderCardProps {
  order: OrderDetail;
  onQuickPrompt: (prompt: string) => void;
  onViewPolicy?: () => void;
}

/** Order summary shown under an assistant message; every value comes from the order itself. */
export const OrderCard: React.FC<OrderCardProps> = ({ order, onQuickPrompt, onViewPolicy }) => {
  const steps = timelineFor(order);
  const [first, ...rest] = order.items;
  const quantity = order.items.reduce((sum, it) => sum + it.qty, 0);
  const title = first ? (rest.length ? `${first.product_name} và ${rest.length} sản phẩm khác` : first.product_name) : 'Đơn hàng';

  return (
    <>
      <div className="ocard">
        <div className="pi">
          <div className="im">
            <PackageIcon />
          </div>
          <div>
            <h4>{title}</h4>
            <div className="meta">
              <span>
                <span className="l">Mã đơn:</span> {order.order_code}
              </span>
              {order.placed_at && <i />}
              {order.placed_at && (
                <span>
                  <span className="l">Ngày đặt:</span> {formatDate(order.placed_at)}
                </span>
              )}
            </div>
            <div className="meta">
              <span>Số lượng: x{quantity}</span>
              <i />
              <span>
                Tổng tiền: <b>{formatVnd(order.total)}</b>
              </span>
            </div>
          </div>
        </div>
        {steps ? (
          <div className="steps">
            {steps.map((step) => (
              <div key={step.label} className={`st${step.reached && step.final ? ' done' : ''}`}>
                <div className="ck" style={step.reached ? undefined : { borderColor: 'var(--bd)', color: 'var(--bd)' }}>
                  <CheckIcon />
                </div>
                <b>{step.label}</b>
                <span>{step.reached ? step.date : ''}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="steps single">
            <span className="ok muted">{statusLabel(order.status)}</span>
          </div>
        )}
      </div>
      {canRequestReturn(order) && (
        <div className="acts">
          <button type="button" className="btn pri" onClick={() => onQuickPrompt(`Tạo yêu cầu đổi trả cho đơn ${order.order_code}`)}>
            <RefreshIcon />
            Tạo yêu cầu đổi trả
          </button>
          {onViewPolicy && (
            <button type="button" className="btn sec" onClick={onViewPolicy}>
              <DocIcon />
              Xem chi tiết chính sách
            </button>
          )}
        </div>
      )}
    </>
  );
};
