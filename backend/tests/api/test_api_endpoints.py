"""Comprehensive integration tests for FastAPI endpoints."""

from __future__ import annotations

import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shopagent.api.app import app
from shopagent.api.deps import get_db_session
from shopagent.core.security import hash_password
from shopagent.infra.db.tables import (
    Base,
    CustomerCredentialsModel,
    CustomerModel,
    OrderItemModel,
    OrderModel,
    ProductModel,
    ProductVariantModel,
    StaffUserModel,
)


@pytest.fixture
async def test_app_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed test customer and staff
    cust_id = uuid.uuid4()
    staff_id = uuid.uuid4()
    order_id = uuid.uuid4()

    async with session_factory() as session:
        cust = CustomerModel(
            id=cust_id,
            email="cust1@example.com",
            phone="0901234567",
            full_name="Nguyễn Văn A",
        )
        creds = CustomerCredentialsModel(
            customer_id=cust_id,
            password_hash=hash_password("Pass1234!"),
        )
        staff = StaffUserModel(
            id=staff_id,
            email="staff1@shoplab.vn",
            role="agent",
            full_name="Nhân viên CSKH",
            password_hash=hash_password("StaffPass123!"),
        )
        session.add(cust)
        session.add(creds)
        session.add(staff)

        # Order
        prod = ProductModel(id=uuid.uuid4(), name="Áo thun", category="fashion")
        var = ProductVariantModel(id=uuid.uuid4(), product_id=prod.id, sku="TS-AO-01", price=250000, stock=10)
        order = OrderModel(
            id=order_id,
            code="SL-TEST01",
            customer_id=cust_id,
            status="confirmed",
            payment_method="card",
            payment_status="paid",
            subtotal=250000,
            discount_total=0,
            shipping_fee=0,
            total=250000,
            paid_amount=250000,
            refunded_amount=0,
        )
        item = OrderItemModel(
            id=uuid.uuid4(),
            order_id=order_id,
            variant_id=var.id,
            qty=1,
            unit_price=250000,
            allocated_discount=0,
            returned_qty=0,
            exchanged=False,
        )
        session.add(prod)
        session.add(var)
        session.add(order)
        session.add(item)
        await session.commit()

    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_health_and_version(test_app_client: AsyncClient):
    res_h = await test_app_client.get("/healthz")
    assert res_h.status_code == 200
    assert res_h.json()["status"] == "ok"

    res_v = await test_app_client.get("/version")
    assert res_v.status_code == 200
    assert res_v.json()["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_customer_auth_and_orders(test_app_client: AsyncClient):
    # 1. Login
    res_login = await test_app_client.post(
        "/auth/login",
        json={"email": "cust1@example.com", "password": "Pass1234!"},
    )
    assert res_login.status_code == 200
    token = res_login.json()["access_token"]
    assert token

    # 2. Get Orders
    headers = {"Authorization": f"Bearer {token}"}
    res_orders = await test_app_client.get("/me/orders", headers=headers)
    assert res_orders.status_code == 200
    orders = res_orders.json()["orders"]
    assert len(orders) == 1
    assert orders[0]["order_code"] == "SL-TEST01"


@pytest.mark.asyncio
async def test_staff_login_and_approvals(test_app_client: AsyncClient):
    res_staff = await test_app_client.post(
        "/staff/auth/login",
        json={"email": "staff1@shoplab.vn", "password": "StaffPass123!"},
    )
    assert res_staff.status_code == 200
    data = res_staff.json()
    assert data["role"] == "agent"

    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_app = await test_app_client.get("/staff/approvals", headers=headers)
    assert res_app.status_code == 200
    assert "approvals" in res_app.json()


@pytest.mark.asyncio
async def test_guest_otp_flow(test_app_client: AsyncClient):
    # 1. Request verification
    res_req = await test_app_client.post(
        "/guest/verifications",
        json={"order_code": "SL-TEST01", "phone": "0901234567"},
    )
    assert res_req.status_code == 202
    v_id = res_req.json()["verification_id"]

    # 2. Wrong OTP
    res_wrong = await test_app_client.post(
        f"/guest/verifications/{v_id}/otp",
        json={"otp": "000000"},
    )
    assert res_wrong.status_code in (400, 404)


@pytest.mark.asyncio
async def test_conversation_and_handoff_flow(test_app_client: AsyncClient):
    # 1. Login
    res_login = await test_app_client.post(
        "/auth/login",
        json={"email": "cust1@example.com", "password": "Pass1234!"},
    )
    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create conversation
    res_conv = await test_app_client.post(
        "/conversations",
        json={"channel": "web"},
        headers=headers,
    )
    assert res_conv.status_code == 200
    conv_id = res_conv.json()["id"]

    # 3. Request human handoff
    res_handoff = await test_app_client.post(
        f"/conversations/{conv_id}/handoff",
        headers=headers,
    )
    assert res_handoff.status_code == 200
    assert res_handoff.json()["status"] == "waiting_human"

    # 4. Staff claims ticket and returns to AI
    res_staff = await test_app_client.post(
        "/staff/auth/login",
        json={"email": "staff1@shoplab.vn", "password": "StaffPass123!"},
    )
    staff_token = res_staff.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    res_tickets = await test_app_client.get("/staff/tickets", headers=staff_headers)
    assert res_tickets.status_code == 200
    tickets = res_tickets.json()["tickets"]
    assert len(tickets) >= 1
    t_id = tickets[0]["id"]

    # Claim ticket
    res_claim = await test_app_client.post(f"/staff/tickets/{t_id}/claim", headers=staff_headers)
    assert res_claim.status_code == 200
    assert res_claim.json()["status"] == "claimed"

    # Return conversation to AI
    res_return = await test_app_client.post(f"/staff/conversations/{conv_id}/return-to-ai", headers=staff_headers)
    assert res_return.status_code == 200
    assert res_return.json()["status"] == "returned_to_ai"


@pytest.mark.asyncio
async def test_conversation_authorization_and_idor_protection(test_app_client: AsyncClient):
    """Test strict IDOR protection for conversations across guests and authenticated customers."""
    # 1. Customer A logs in and creates a conversation
    res_login = await test_app_client.post(
        "/auth/login",
        json={"email": "cust1@example.com", "password": "Pass1234!"},
    )
    cust_token = res_login.json()["access_token"]
    cust_headers = {"Authorization": f"Bearer {cust_token}"}

    res_conv_a = await test_app_client.post("/conversations", json={"channel": "web"}, headers=cust_headers)
    assert res_conv_a.status_code == 200
    conv_a_id = res_conv_a.json()["id"]

    # 2. Guest attempts to read Customer A's conversation without token -> 403 Forbidden
    res_unauth_get = await test_app_client.get(f"/conversations/{conv_a_id}")
    assert res_unauth_get.status_code == 403

    # 3. Guest attempts to send message to Customer A's conversation -> 403 Forbidden
    res_unauth_post = await test_app_client.post(
        f"/conversations/{conv_a_id}/messages",
        json={"content": "Hacker injection message"},
    )
    assert res_unauth_post.status_code == 403

    # 4. Guest attempts to open SSE stream of Customer A's conversation -> 403 Forbidden
    res_unauth_sse = await test_app_client.get(f"/conversations/{conv_a_id}/events")
    assert res_unauth_sse.status_code == 403

    # 5. Guest creates own conversation and receives secure guest_token
    res_guest_conv = await test_app_client.post("/conversations", json={"channel": "web"})
    assert res_guest_conv.status_code == 200
    guest_conv_data = res_guest_conv.json()
    guest_conv_id = guest_conv_data["id"]
    guest_token = guest_conv_data["guest_token"]
    assert guest_token is not None and len(guest_token) >= 32

    # 6. Another guest with an invalid guest_token attempts to access -> 403 Forbidden
    res_invalid_token = await test_app_client.get(
        f"/conversations/{guest_conv_id}",
        headers={"X-Guest-Token": "invalid_fake_token"},
    )
    assert res_invalid_token.status_code == 403

    # 7. Guest with legitimate guest_token accesses successfully -> 200 OK
    res_valid_token = await test_app_client.get(
        f"/conversations/{guest_conv_id}",
        headers={"X-Guest-Token": guest_token},
    )
    assert res_valid_token.status_code == 200

