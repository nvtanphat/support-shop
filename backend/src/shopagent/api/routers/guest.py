"""Guest customer OTP verification endpoints with strict security:
- Expiry check (5-minute TTL)
- Anti-replay protection (instant invalidation upon verification)
- Brute-force protection (max 5 failed attempts)
- Rate limiting (minimum 60s cooldown, max 3 requests per 5 minutes per phone)
"""

from __future__ import annotations

import random
import time
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

# Verification state: {verification_id: {"order_id": ..., "otp": ..., "attempts": ..., "expires_at": ...}}
_GUEST_VERIFICATIONS: dict[str, dict[str, Any]] = {}

# Rate limit tracking: {phone: [timestamp1, timestamp2, ...]}
_RATE_LIMIT_STORE: dict[str, list[float]] = {}
_COOLDOWN_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 3
_WINDOW_SECONDS = 300  # 5 minutes


def _enforce_rate_limit(phone: str, now: float) -> None:
    """Enforce minimum cooldown and request window rate limiting per phone."""
    history = _RATE_LIMIT_STORE.get(phone, [])
    # Filter out timestamps older than the window
    history = [t for t in history if now - t < _WINDOW_SECONDS]
    _RATE_LIMIT_STORE[phone] = history

    if history:
        # Check cooldown from the latest request
        latest = history[-1]
        if now - latest < _COOLDOWN_SECONDS:
            remaining = int(_COOLDOWN_SECONDS - (now - latest))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Quý khách vui lòng đợi {remaining} giây trước khi yêu cầu mã OTP tiếp theo.",
            )

    if len(history) >= _MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Quý khách đã yêu cầu mã OTP quá 3 lần trong 5 phút. Vui lòng thử lại sau.",
        )

    history.append(now)


@router.post("/verifications", status_code=status.HTTP_202_ACCEPTED)
async def request_guest_verification(
    req: GuestVerificationRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Initiate guest order lookup verification via OTP. Always returns 202 to prevent order probing."""
    verification_id = str(uuid.uuid4())
    clock = get_clock()
    now_ts = clock.now().timestamp()

    clean_req_phone = req.phone.strip().replace(" ", "").replace("-", "")

    # Apply rate limiting per phone number
    _enforce_rate_limit(clean_req_phone, now_ts)

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
        clean_db_phone = customer.phone.strip().replace(" ", "").replace("-", "")
        if clean_req_phone.endswith(clean_db_phone[-9:]):
            otp = f"{random.randint(100000, 999999)}"
            _GUEST_VERIFICATIONS[verification_id] = {
                "order_id": order.id,
                "order_code": order.code,
                "customer_id": customer.id,
                "otp": otp,
                "attempts": 0,
                "expires_at": now_ts + 300,  # Strict 5-minute expiry
            }

    settings = get_settings()
    resp: dict[str, Any] = {
        "status": "accepted",
        "verification_id": verification_id,
        "message": "Nếu thông tin đơn hàng và số điện thoại chính xác, mã xác nhận OTP gồm 6 chữ số đã được gửi qua SMS.",
    }
    # In simulated mode, return simulated_otp so automated tests and manual tests can proceed without real SMS gateway
    if settings.INTEGRATION_MODE == "simulated" and verification_id in _GUEST_VERIFICATIONS:
        resp["simulated_otp"] = _GUEST_VERIFICATIONS[verification_id]["otp"]

    return resp


@router.post("/verifications/{verification_id}/otp")
async def verify_guest_otp(
    verification_id: str,
    req: GuestVerifyOtpRequest,
):
    """Verify OTP code to grant temporary access to order details.
    
    Enforces expiry, attempts limit, and instant invalidation to prevent replay attacks.
    """
    clock = get_clock()
    now_ts = clock.now().timestamp()

    record = _GUEST_VERIFICATIONS.get(verification_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phiên xác minh không tồn tại hoặc đã bị hủy.",
        )

    # 1. Expiry Check
    if now_ts > record["expires_at"]:
        _GUEST_VERIFICATIONS.pop(verification_id, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã OTP đã hết hạn. Vui lòng yêu cầu mã xác minh mới.",
        )

    # 2. Brute Force Protection (max 5 attempts)
    if record["attempts"] >= 5:
        _GUEST_VERIFICATIONS.pop(verification_id, None)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Bạn đã nhập sai OTP quá 5 lần. Phiên xác minh đã bị hủy để đảm bảo an toàn.",
        )

    record["attempts"] += 1

    # 3. Code Match Check
    if req.otp != record["otp"]:
        remaining = 5 - record["attempts"]
        if remaining <= 0:
            _GUEST_VERIFICATIONS.pop(verification_id, None)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Bạn đã nhập sai OTP quá 5 lần. Phiên xác minh đã bị hủy.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mã OTP không chính xác. Còn lại {remaining} lần thử.",
        )

    # 4. Anti-Replay: Pop immediately upon success so OTP cannot be reused
    _GUEST_VERIFICATIONS.pop(verification_id, None)

    # 5. Create temporary guest JWT token with verified_order_id grant for 30 minutes
    guest_token = create_access_token(
        data={
            "sub": str(record["customer_id"]),
            "role": "guest",
            "verified_order_id": str(record["order_id"]),
            "order_code": record["order_code"],
        },
    )

    return {
        "status": "verified",
        "guest_token": guest_token,
        "order_code": record["order_code"],
        "granted_for_minutes": 30,
        "message": "Xác minh thành công. Bạn có thể tra cứu đơn hàng này.",
    }
