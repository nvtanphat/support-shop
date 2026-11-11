"""Customer orders and cases data endpoints."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.api.deps import get_current_principal, get_db_session, require_authenticated
from shopagent.core.errors import AppError, ForbiddenError, NotFoundError
from shopagent.core.principal import Principal
from shopagent.domain.services.orders import OrderService
from shopagent.infra.db.tables import RefundModel, ReturnRequestModel, TicketModel

router = APIRouter(tags=["Orders & Customer Data"])


@router.get("/orders/{code}")
async def get_order_by_code(
    code: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
):
    """Fetch order details dynamically for authorized customer or guest."""
    order_service = OrderService(session)
    clean_code = code.strip().upper()
    try:
        return await order_service.get_order_for_principal(principal, order_code=clean_code)
    except ForbiddenError:
        # Return safe masked summary for guest preview if OTP not yet completed
        order = await order_service.order_repo.get_by_code(clean_code)
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy đơn hàng {clean_code}.")
        first_item = order.items[0] if order.items else None
        prod_name = first_item.variant.product.name if first_item and first_item.variant and first_item.variant.product else "Sản phẩm"
        return {
            "order_id": str(order.id),
            "order_code": order.code,
            "status": order.status,
            "payment_method": order.payment_method,
            "total": order.total,
            "placed_at": order.placed_at.isoformat() if order.placed_at else None,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "is_guest_preview": True,
            "items": [
                {
                    "item_id": str(it.id),
                    "product_name": it.variant.product.name if it.variant and it.variant.product else prod_name,
                    "qty": it.qty,
                    "unit_price": it.unit_price,
                }
                for it in order.items
            ],
        }
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/me/orders")
async def get_my_orders(
    status: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    principal: Principal = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
):
    """List authenticated customer orders."""
    order_service = OrderService(session)
    orders = await order_service.list_orders_for_principal(principal, status=status, limit=limit)
    return {"orders": orders, "count": len(orders)}


@router.get("/me/orders/{code}")
async def get_my_order_detail(
    code: str,
    principal: Principal = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
):
    """Get full details of a specific customer order."""
    order_service = OrderService(session)
    try:
        return await order_service.get_order_for_principal(principal, order_code=code)
    except AppError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/me/cases")
async def get_my_cases(
    principal: Principal = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
):
    """List customer return requests, refunds, and support tickets."""
    cust_id = principal.customer_id

    stmt_ret = select(ReturnRequestModel).where(ReturnRequestModel.customer_id == cust_id)
    res_ret = await session.execute(stmt_ret)
    returns = res_ret.scalars().all()

    stmt_rf = select(RefundModel).join(ReturnRequestModel).where(ReturnRequestModel.customer_id == cust_id)
    res_rf = await session.execute(stmt_rf)
    refunds = res_rf.scalars().all()

    stmt_tk = select(TicketModel).where(TicketModel.customer_id == cust_id)
    res_tk = await session.execute(stmt_tk)
    tickets = res_tk.scalars().all()

    return {
        "returns": [{"code": r.code, "status": r.status, "reason": r.reason_code} for r in returns],
        "refunds": [{"code": rf.code, "status": rf.status, "amount": rf.amount} for rf in refunds],
        "tickets": [{"code": t.code, "status": t.status, "priority": t.priority} for t in tickets],
    }
