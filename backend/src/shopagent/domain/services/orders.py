"""Order domain service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.errors import ForbiddenError, NotFoundError
from shopagent.core.principal import Principal
from shopagent.domain.models.enums import OrderStatus
from shopagent.infra.carriers.port import CarrierPort
from shopagent.infra.db.repositories.order_repo import OrderRepository


class OrderService:
    def __init__(self, session: AsyncSession, carrier_port: CarrierPort | None = None) -> None:
        self.session = session
        self.order_repo = OrderRepository(session)
        self.carrier_port = carrier_port

    async def get_order_for_principal(
        self, principal: Principal, order_code: str
    ) -> dict[str, Any]:
        """Fetch order details if principal is authorized.

        Enforces ownership check.
        """
        order = await self.order_repo.get_by_code(order_code)
        if not order:
            raise NotFoundError(
                f"Không tìm thấy đơn hàng có mã '{order_code}'.",
                error_code="ORDER_NOT_FOUND",
                hint="Vui lòng kiểm tra lại mã đơn hàng hoặc tra danh sách đơn gần đây.",
            )

        if not principal.can_access_order(order.customer_id, order.id):
            raise ForbiddenError(
                "Bạn không có quyền truy cập thông tin của đơn hàng này.",
                error_code="ORDER_ACCESS_DENIED",
            )

        # Build clean representation
        items_dto = [
            {
                "item_id": str(it.id),
                "sku": it.variant.sku if it.variant else "",
                "product_name": it.variant.product.name if it.variant and it.variant.product else "",
                "qty": it.qty,
                "unit_price": it.unit_price,
                "allocated_discount": it.allocated_discount,
                "returned_qty": it.returned_qty,
                "remaining_qty": max(0, it.qty - it.returned_qty),
                "exchanged": it.exchanged,
                "category": it.variant.product.category if it.variant and it.variant.product else "general",
                "return_flags": it.variant.product.return_flags if it.variant and it.variant.product else [],
            }
            for it in order.items
        ]

        # Determine available user actions
        available_actions: list[dict[str, str]] = []
        if order.status in (OrderStatus.PENDING_PAYMENT.value, OrderStatus.CONFIRMED.value):
            available_actions.append({"action": "cancel", "type": "self_service", "label": "Hủy đơn hàng"})
        elif order.status == OrderStatus.PACKING.value:
            available_actions.append({"action": "cancel", "type": "requires_approval", "label": "Yêu cầu hủy đơn (chờ duyệt)"})
        elif order.status in (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value):
            available_actions.append({"action": "return", "type": "eligible_check", "label": "Yêu cầu trả hàng / hoàn tiền"})
            available_actions.append({"action": "exchange", "type": "eligible_check", "label": "Yêu cầu đổi hàng"})

        return {
            "order_id": str(order.id),
            "order_code": order.code,
            "status": order.status,
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "subtotal": order.subtotal,
            "discount_total": order.discount_total,
            "shipping_fee": order.shipping_fee,
            "total": order.total,
            "channel": order.channel,
            "policy_version": order.policy_version,
            "placed_at": order.placed_at.isoformat() if order.placed_at else None,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "items": items_dto,
            "available_actions": available_actions,
            # Mask sensitive untrusted text if any
            "untrusted_note": order.note[:100] if order.note else None,
        }

    async def list_orders_for_principal(
        self, principal: Principal, status: OrderStatus | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        if not principal.is_authenticated_customer or principal.customer_id is None:
            raise ForbiddenError("Chức năng xem danh sách đơn hàng chỉ áp dụng cho khách đã đăng nhập.")

        orders = await self.order_repo.list_by_customer(
            customer_id=principal.customer_id, status=status, limit=min(limit, 5)
        )
        return [
            {
                "order_code": o.code,
                "status": o.status,
                "total": o.total,
                "placed_at": o.placed_at.isoformat() if o.placed_at else None,
                "item_count": len(o.items),
                "summary_items": [f"{it.qty}x {it.variant.sku if it.variant else 'SP'}" for it in o.items[:2]],
            }
            for o in orders
        ]
