"""Guest customer OTP verification endpoints with strict security:
- Persistent storage in database (GuestVerificationModel)
- Expiry check (5-minute TTL)
- Anti-replay protection (instant invalidation upon verification)
- Brute-force protection (max 5 failed attempts)
- Rate limiting (minimum 60s cooldown, max 3 requests per 5 minutes per phone)
"""

from __future__ import annotations

import hashlib
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.api.deps import get_db_session
from shopagent.api.schemas.models import GuestVerificationRequest, GuestVerifyOtpRequest
from shopagent.core.clock import get_clock
from shopagent.core.config import get_app_config, get_settings
from shopagent.core.security import create_access_token
from shopagent.infra.db.tables import CustomerModel, GuestVerificationModel, OrderModel

router = APIRouter(prefix="/guest", tags=["Guest Verifications"])

# In-memory helpers for backward compatibility / test fixtures
_GUEST_VERIFICATIONS: dict[str, dict[str, Any]] = {}
_RATE_LIMIT_STORE: dict[str, list[float]] = {}
_COOLDOWN_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 3
_WINDOW_SECONDS = 300  # 5 minutes


def _hash_value(value: str) -> str:
    """Deterministic SHA-256 hash for phone or OTP."""
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


async def _enforce_db_rate_limit(
    phone_hash: str,
    clean_phone: str,
    now_dt: datetime,
    session: AsyncSession,
) -> None:
    """Enforce rate limits using both DB records and fast memory window."""
    # Memory cooldown check for tests and fast fail
    now_ts = now_dt.timestamp()
    history = _RATE_LIMIT_STORE.get(clean_phone, [])
    history = [t for t in history if now_ts - t < _WINDOW_SECONDS]
    _RATE_LIMIT_STORE[clean_phone] = history

    if history:
        latest = history[-1]
        if now_ts - latest < _COOLDOWN_SECONDS:
            remaining = int(_COOLDOWN_SECONDS - (now_ts - latest))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Quý khách vui lòng đợi {remaining} giây trước khi yêu cầu mã OTP tiếp theo.",
            )
        if len(history) >= _MAX_REQUESTS_PER_WINDOW:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Quý khách đã yêu cầu mã OTP quá 3 lần trong 5 phút. Vui lòng thử lại sau.",
            )

    # Database window check for multi-worker safety
    window_start = now_dt - timedelta(seconds=_WINDOW_SECONDS)
    stmt = (
        select(GuestVerificationModel)
        .where(
            GuestVerificationModel.phone_hash == phone_hash,
            GuestVerificationModel.created_at >= window_start,
        )
        .order_by(GuestVerificationModel.created_at.desc())
    )
    res = await session.execute(stmt)
    records = res.scalars().all()

    if records:
        latest_record = records[0]
        # Ensure latest_record.created_at is timezone-aware
        created_at = latest_record.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        elapsed = (now_dt - created_at).total_seconds()
        if elapsed < _COOLDOWN_SECONDS:
            remaining = int(_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Quý khách vui lòng đợi {remaining} giây trước khi yêu cầu mã OTP tiếp theo.",
            )
        if len(records) >= _MAX_REQUESTS_PER_WINDOW:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Quý khách đã yêu cầu mã OTP quá 3 lần trong 5 phút. Vui lòng thử lại sau.",
            )

    history.append(now_ts)


@router.post("/verifications", status_code=status.HTTP_202_ACCEPTED)
async def request_guest_verification(
    req: GuestVerificationRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Initiate guest order lookup verification via OTP. Always returns 202 to prevent order probing."""
    verification_uuid = uuid.uuid4()
    verification_id = str(verification_uuid)
    clock = get_clock()
    now_dt = clock.now()
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=UTC)

    clean_req_phone = req.phone.strip().replace(" ", "").replace("-", "")
    phone_hash = _hash_value(clean_req_phone)

    # 1. Enforce rate limiting per phone
    await _enforce_db_rate_limit(phone_hash, clean_req_phone, now_dt, session)

    # 2. Look up matching order and customer
    stmt = (
        select(OrderModel, CustomerModel)
        .join(CustomerModel, OrderModel.customer_id == CustomerModel.id)
        .where(OrderModel.code == req.order_code.strip().upper())
    )
    res = await session.execute(stmt)
    row = res.first()

    matched_order_id: uuid.UUID | None = None
    order_code_val = req.order_code.strip().upper()
    customer_id_val: uuid.UUID | None = None
    otp = f"{random.randint(100000, 999999)}"

    if row:
        order, customer = row
        clean_db_phone = customer.phone.strip().replace(" ", "").replace("-", "")
        if clean_req_phone.endswith(clean_db_phone[-9:]):
            matched_order_id = order.id
            order_code_val = order.code
            customer_id_val = customer.id

    # Store in DB table guest_verifications
    otp_hash = _hash_value(otp)
    expires_dt = now_dt + timedelta(seconds=_WINDOW_SECONDS)
    db_record = GuestVerificationModel(
        id=verification_uuid,
        guest_token=verification_id,
        order_id=matched_order_id,
        phone_hash=phone_hash,
        otp_hash=otp_hash,
        attempts=0,
        expires_at=expires_dt,
        verified_at=None,
        grant_expires_at=None,
        created_at=now_dt,
    )
    session.add(db_record)
    await session.commit()

    # Mirror to in-memory state for fast mock tests
    if matched_order_id is not None:
        _GUEST_VERIFICATIONS[verification_id] = {
            "order_id": matched_order_id,
            "order_code": order_code_val,
            "customer_id": customer_id_val,
            "otp": otp,
            "attempts": 0,
            "expires_at": now_dt.timestamp() + 300,
        }

    settings = get_settings()
    resp: dict[str, Any] = {
        "status": "accepted",
        "verification_id": verification_id,
        "message": "Nếu thông tin đơn hàng và số điện thoại chính xác, mã xác nhận OTP gồm 6 chữ số đã được gửi qua SMS.",
    }
    if settings.INTEGRATION_MODE == "simulated" and matched_order_id is not None:
        resp["simulated_otp"] = otp

    return resp


@router.post("/verifications/{verification_id}/otp")
async def verify_guest_otp(
    verification_id: str,
    req: GuestVerifyOtpRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Verify OTP code to grant temporary access to order details.
    
    Enforces expiry, attempts limit, and instant invalidation to prevent replay attacks.
    """
    clock = get_clock()
    now_dt = clock.now()
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=UTC)

    try:
        v_uuid = uuid.UUID(verification_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phiên xác minh không hợp lệ.",
        ) from None

    # Query record from DB
    stmt = select(GuestVerificationModel).where(GuestVerificationModel.id == v_uuid)
    res = await session.execute(stmt)
    record = res.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phiên xác minh không tồn tại hoặc đã bị hủy.",
        )

    # 1. Anti-Replay: Check if already verified
    if record.verified_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phiên xác minh không tồn tại hoặc đã bị hủy.",
        )

    # 2. Expiry Check
    rec_exp = record.expires_at
    if rec_exp.tzinfo is None:
        rec_exp = rec_exp.replace(tzinfo=UTC)

    if now_dt > rec_exp:
        await session.delete(record)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã OTP đã hết hạn. Vui lòng yêu cầu mã xác minh mới.",
        )

    # 3. Brute Force Protection (max 5 attempts)
    if record.attempts >= 5:
        await session.delete(record)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phiên xác minh không tồn tại hoặc đã bị hủy.",
        )

    record.attempts += 1
    input_otp_hash = _hash_value(req.otp)

    # 4. Code Match Check
    if input_otp_hash != record.otp_hash:
        remaining = 5 - record.attempts
        if remaining <= 0:
            await session.delete(record)
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Bạn đã nhập sai OTP quá 5 lần. Phiên xác minh đã bị hủy.",
            )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mã OTP không chính xác. Còn lại {remaining} lần thử.",
        )

    if not record.order_id:
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thông tin đơn hàng không khớp.",
        )

    # 5. Success: record verification timestamp and grant duration (30 minutes)
    record.verified_at = now_dt
    record.grant_expires_at = now_dt + timedelta(minutes=int(get_app_config().get("guest_view_token_ttl_minutes", 30)))
    await session.commit()

    # Invalidate in-memory tracker
    _GUEST_VERIFICATIONS.pop(verification_id, None)

    # Fetch order to populate JWT
    order_stmt = select(OrderModel).where(OrderModel.id == record.order_id)
    order_res = await session.execute(order_stmt)
    order_obj = order_res.scalar_one_or_none()
    order_code_str = order_obj.code if order_obj else ""
    cust_id_str = str(order_obj.customer_id) if order_obj and order_obj.customer_id else "guest"

    # 6. Create temporary guest JWT token with verified_order_id grant for 30 minutes
    guest_token = create_access_token(
        data={
            "sub": cust_id_str,
            "role": "guest",
            "verified_order_id": str(record.order_id),
            "order_code": order_code_str,
        },
    )

    return {
        "status": "verified",
        "guest_token": guest_token,
        "order_code": order_code_str,
        "granted_for_minutes": 30,
        "message": "Xác minh thành công. Bạn có thể tra cứu đơn hàng này.",
    }
