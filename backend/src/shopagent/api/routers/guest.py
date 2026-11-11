"""Guest customer OTP verification endpoints."""

from __future__ import annotations

import random
from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.api.deps import get_db_session
from shopagent.api.schemas.models import GuestVerificationRequest, GuestVerifyOtpRequest
from shopagent.core.clock import get_clock
from shopagent.core.config import get_settings
from shopagent.core.security import create_access_token
from shopagent.infra.db.tables import CustomerModel, OrderModel

router = APIRouter(prefix="/guest", tags=["Guest Verifications"])

# In-memory OTP storage for simulated mode: {verification_id: {"order_id": ..., "otp": ..., "attempts": ...}}
_GUEST_VERIFICATIONS: dict[str, dict[str, Any]] = {}


@router.post("/verifications", status_code=status.HTTP_202_ACCEPTED)
async def request_guest_verification(
    req: GuestVerificationRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Initiate guest order lookup verification via OTP. Always returns 202 to prevent order probing."""
    verification_id = str(uuid.uuid4())
    clock = get_clock()

    # Find order and customer
    stmt = (
        select(OrderModel, CustomerModel)
        .join(CustomerModel, OrderModel.customer_id == CustomerModel.id)
        .where(OrderModel.code == req.order_code.strip().upper())
    )
    res = await session.execute(stmt)
    row = res.first()

    if row:
        order, customer = row
        # Normalize phone
        clean_req_phone = req.phone.strip().replace(" ", "").replace("-", "")
        clean_db_phone = customer.phone.strip().replace(" ", "").replace("-", "")
        if clean_req_phone.endswith(clean_db_phone[-9:]):
            otp = f"{random.randint(100000, 999999)}"
            _GUEST_VERIFICATIONS[verification_id] = {
                "order_id": order.id,
                "order_code": order.code,
                "customer_id": customer.id,
                "otp": otp,
                "attempts": 0,
                "expires_at": clock.now().timestamp() + 900,  # 15 minutes
            }

    settings = get_settings()
    resp: dict[str, Any] = {
        "status": "accepted",
        "verification_id": verification_id,
        "message": "Nếu thông tin đơn hàng và số điện thoại chính xác, mã xác nhận OTP gồm 6 chữ số đã được gửi qua SMS.",
    }
    # In simulated mode, return simulated_otp so clients can test without real SMS gateway
    if settings.INTEGRATION_MODE == "simulated" and verification_id in _GUEST_VERIFICATIONS:
        resp["simulated_otp"] = _GUEST_VERIFICATIONS[verification_id]["otp"]

    return resp


@router.post("/verifications/{verification_id}/otp")
async def verify_guest_otp(
    verification_id: str,
    req: GuestVerifyOtpRequest,
):
    """Verify OTP code to grant temporary access to order details."""
    record = _GUEST_VERIFICATIONS.get(verification_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phiên xác minh không tồn tại hoặc đã hết hạn.")

    if record["attempts"] >= 5:
        _GUEST_VERIFICATIONS.pop(verification_id, None)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Bạn đã nhập sai OTP quá 5 lần.")

    record["attempts"] += 1
    if req.otp != record["otp"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã OTP không chính xác.")

    # Create temporary guest JWT token with verified_order_id grant for 30 minutes
    guest_token = create_access_token(
        data={
            "sub": str(record["customer_id"]),
            "role": "guest",
            "verified_order_id": str(record["order_id"]),
            "order_code": record["order_code"],
        },
        expires_minutes=30,
    )

    # Verification successful
    return {
        "status": "verified",
        "guest_token": guest_token,
        "order_code": record["order_code"],
        "granted_for_minutes": 30,
        "message": "Xác minh thành công. Bạn có thể tra cứu đơn hàng này.",
    }
