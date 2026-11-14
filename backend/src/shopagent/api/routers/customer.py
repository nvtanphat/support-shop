"""Customer orders and cases data endpoints."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.api.deps import get_current_principal, get_db_session, require_authenticated
from shopagent.core.errors import AppError, ForbiddenError, NotFoundError
from shopagent.core.principal import Principal
from shopagent.domain.models.enums import OrderStatus
from shopagent.domain.services.orders import OrderService
from shopagent.infra.db.tables import RefundModel, ReturnRequestModel, TicketModel

router = APIRouter(tags=["Orders & Customer Data"])

_ORDER_NOT_FOUND_DETAIL = "Không tìm thấy đơn hàng này trong tài khoản của quý khách."
_GUEST_VERIFICATION_DETAIL = (
    "Bạn không có quyền truy cập thông tin đơn hàng này. "
    "Vui lòng xác thực OTP qua số điện thoại mua hàng hoặc đăng nhập."
)


@router.get("/orders/{code}")
async def get_order_by_code(
    code: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
):
    """Fetch order details dynamically for authorized customer or verified guest."""
    order_service = OrderService(session)
    clean_code = code.strip().upper()
    try:
        return await order_service.get_order_for_principal(principal, order_code=clean_code)
    except (ForbiddenError, NotFoundError):
        # "Not yours" and "does not exist" must look the same, or order codes can be probed.
        if principal.is_guest:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_GUEST_VERIFICATION_DETAIL) from None
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ORDER_NOT_FOUND_DETAIL) from None


@router.get("/me/orders")
async def get_my_orders(
    status: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    principal: Principal = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
):
    """List authenticated customer orders."""
    order_service = OrderService(session)
    status_enum = None
    if status:
        with contextlib.suppress(ValueError):
            status_enum = OrderStatus(status.lower())
    orders = await order_service.list_orders_for_principal(principal, status=status_enum, limit=limit)
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
        return await order_service.get_order_for_principal(principal, order_code=code.strip().upper())
    except AppError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ORDER_NOT_FOUND_DETAIL) from None


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
