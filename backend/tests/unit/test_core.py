"""Unit tests for shopagent.core modules."""

from datetime import datetime

from shopagent.core.clock import (
    STORE_TIMEZONE,
    compute_deadline_days_end_of_day,
)
from shopagent.core.ids import (
    generate_order_code,
)
from shopagent.core.principal import Principal, PrincipalRole
from shopagent.core.security import (
    compute_preview_hash,
    hash_password,
    mask_email,
    mask_phone,
    mask_pii_text,
    verify_password,
)


def test_clock_deadline_end_of_local_day() -> None:
    # 23:30 on 2026-11-01 in Vietnam (Asia/Ho_Chi_Minh) is 16:30 UTC on 2026-11-01
    dt_local = datetime(2026, 11, 1, 23, 30, tzinfo=STORE_TIMEZONE)
    # 7 days deadline should be 23:59:59 on 2026-11-08 Vietnam time
    deadline_utc = compute_deadline_days_end_of_day(dt_local, days=7)
    deadline_local = deadline_utc.astimezone(STORE_TIMEZONE)

    assert deadline_local.year == 2026
    assert deadline_local.month == 11
    assert deadline_local.day == 8
    assert deadline_local.hour == 23
    assert deadline_local.minute == 59
    assert deadline_local.second == 59


def test_crockford_codes() -> None:
    code = generate_order_code()
    assert code.startswith("SL-")
    assert len(code) == 9  # SL- + 6 chars
    # Ensure no ambiguous characters: I, L, O, U
    raw = code.split("-")[1]
    for ch in ("I", "L", "O", "U"):
        assert ch not in raw


def test_preview_hash_deterministic() -> None:
    payload1 = {"order_code": "SL-123456", "items": ["item1"], "refund_amount": 100000}
    payload2 = {"refund_amount": 100000, "items": ["item1"], "order_code": "SL-123456"}
    h1 = compute_preview_hash(payload1)
    h2 = compute_preview_hash(payload2)
    assert h1 == h2
    assert len(h1) == 64


def test_pii_masking() -> None:
    assert mask_phone("0912345678") == "***678"
    assert mask_phone("+84987654321") == "***321"
    assert mask_email("lan.pham@example.test") == "l***m@example.test"

    text = "Số điện thoại của mình là 0987654321 và cccd 012345678901"
    masked = mask_pii_text(text)
    assert "0987654321" not in masked
    assert "***321" in masked
    assert "[CCCD_ĐÃ_CHE]" in masked


def test_password_hashing() -> None:
    pw = "SuperSecret123!"
    h = hash_password(pw)
    assert verify_password(pw, h)
    assert not verify_password("WrongPassword", h)


def test_principal_order_access() -> None:
    import uuid
    cust_id = uuid.uuid4()
    other_cust_id = uuid.uuid4()
    order_id = uuid.uuid4()

    p_cust = Principal(role=PrincipalRole.CUSTOMER, customer_id=cust_id)
    assert p_cust.can_access_order(cust_id, order_id) is True
    assert p_cust.can_access_order(other_cust_id, order_id) is False

    p_guest_unverified = Principal(role=PrincipalRole.GUEST)
    assert p_guest_unverified.can_access_order(cust_id, order_id) is False

    p_guest_verified = Principal(role=PrincipalRole.GUEST, verified_order_id=order_id)
    assert p_guest_verified.can_access_order(cust_id, order_id) is True
    assert p_guest_verified.can_access_order(cust_id, uuid.uuid4()) is False

    p_staff = Principal(role=PrincipalRole.STAFF_AGENT)
    assert p_staff.can_access_order(cust_id, order_id) is True
