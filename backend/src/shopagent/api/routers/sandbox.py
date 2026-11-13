"""Fault-injection and time-control endpoints. Mounted only when INTEGRATION_MODE=simulated; admin only."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.api.deps import get_db_session, require_staff_role
from shopagent.api.schemas.models import SandboxClockRequest, SandboxFailNextRequest
from shopagent.core.clock import get_clock
from shopagent.core.principal import Principal
from shopagent.infra.db.tables import ShipmentEventModel, ShipmentModel
from shopagent.infra.payments.simulated import get_simulated_gateway

router = APIRouter(prefix="/sandbox", tags=["Sandbox"])

_NEXT_STATUS = {"shipped": "in_transit", "in_transit": "out_for_delivery", "out_for_delivery": "delivered"}


@router.post("/shipments/{tracking_code}/advance")
async def advance_shipment(
    tracking_code: str,
    principal: Principal = Depends(require_staff_role(["admin"])),
    session: AsyncSession = Depends(get_db_session),
):
    """Move a shipment one step along shipped, in transit, out for delivery, delivered."""
    shipment = (await session.execute(select(ShipmentModel).where(ShipmentModel.tracking_code == tracking_code))).scalar_one_or_none()
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy vận đơn.")
    next_status = _NEXT_STATUS.get(shipment.status)
    if next_status is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Vận đơn đang ở trạng thái cuối: {shipment.status}.")
    shipment.status = next_status
    session.add(ShipmentEventModel(id=uuid.uuid4(), shipment_id=shipment.id, status=next_status, location="Sandbox", occurred_at=get_clock().now()))
    await session.commit()
    return {"tracking_code": tracking_code, "status": next_status}


@router.post("/payments/fail-next")
async def fail_next_payment(
    req: SandboxFailNextRequest,
    principal: Principal = Depends(require_staff_role(["admin"])),
):
    """Make the next simulated refund fail once, to exercise retry and reconciliation."""
    get_simulated_gateway().inject_failure_next(req.message)
    return {"status": "armed"}


@router.post("/clock")
async def set_clock(
    req: SandboxClockRequest,
    principal: Principal = Depends(require_staff_role(["admin"])),
):
    """Freeze the application clock at the given ISO time, or release it."""
    clock = get_clock()
    try:
        clock.set_fixed_now(datetime.fromisoformat(req.now) if req.now else None)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Thời điểm phải theo định dạng ISO 8601.") from None
    return {"now": clock.now().isoformat(), "frozen": req.now is not None}
