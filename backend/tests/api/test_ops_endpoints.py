"""Token refresh, feedback, staff audit and metrics, and the sandbox controls."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from shopagent.api.app import app
from shopagent.api.deps import get_db_session
from shopagent.core.clock import get_clock
from shopagent.core.security import create_access_token, hash_password
from shopagent.infra.db.tables import (
    Base,
    CustomerCredentialsModel,
    CustomerModel,
    OrderModel,
    ShipmentModel,
    StaffUserModel,
)
from shopagent.infra.payments.simulated import get_simulated_gateway
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

CUSTOMER_ID = uuid.uuid4()
OTHER_ID = uuid.uuid4()
STAFF = {role: uuid.uuid4() for role in ("agent", "supervisor", "admin")}


def bearer(sub: uuid.UUID, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(sub), 'email': 'x@example.com', 'role': role})}"}


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        for cid, mail, phone in ((CUSTOMER_ID, "a@example.com", "0901234567"), (OTHER_ID, "b@example.com", "0907654321")):
            session.add(CustomerModel(id=cid, email=mail, phone=phone, full_name="Khách"))
            session.add(CustomerCredentialsModel(customer_id=cid, password_hash=hash_password("Pass1234!")))
        for role, sid in STAFF.items():
            session.add(StaffUserModel(id=sid, email=f"{role}@shop.vn", role=role, full_name=role, password_hash=hash_password("x")))
        await session.commit()

    async def override():  # type: ignore[no-untyped-def]
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, factory
    app.dependency_overrides.clear()
    get_clock().set_fixed_now(None)
    await engine.dispose()


async def new_conversation(c: AsyncClient, headers: dict[str, str]) -> str:
    resp = await c.post("/conversations", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    return str(resp.json()["id"])


@pytest.mark.asyncio
async def test_refresh_issues_a_working_token_and_rejects_anonymous_and_deleted_accounts(client) -> None:  # type: ignore[no-untyped-def]
    c, _ = client
    assert (await c.post("/auth/refresh")).status_code == 401
    refreshed = await c.post("/auth/refresh", headers=bearer(CUSTOMER_ID, "customer"))
    assert refreshed.status_code == 200 and refreshed.json()["user_id"] == str(CUSTOMER_ID)
    assert (await c.get("/me/orders", headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"})).status_code == 200
    assert (await c.post("/auth/refresh", headers=bearer(uuid.uuid4(), "customer"))).status_code == 401
    assert (await c.post("/auth/logout")).status_code == 204


@pytest.mark.asyncio
async def test_feedback_is_recorded_for_the_owner_only_and_validates_the_rating(client) -> None:  # type: ignore[no-untyped-def]
    c, _ = client
    owner = bearer(CUSTOMER_ID, "customer")
    conv = await new_conversation(c, owner)
    assert (await c.post(f"/conversations/{conv}/feedback", json={"rating": 5, "comment": "tốt"}, headers=owner)).status_code == 201
    assert (await c.post(f"/conversations/{conv}/feedback", json={"rating": 6}, headers=owner)).status_code == 422
    assert (await c.post(f"/conversations/{conv}/feedback", json={"rating": 1}, headers=bearer(OTHER_ID, "customer"))).status_code == 403
    assert (await c.post(f"/conversations/{uuid.uuid4()}/feedback", json={"rating": 3}, headers=owner)).status_code == 404

    metrics = (await c.get("/staff/metrics", headers=bearer(STAFF["supervisor"], "supervisor"))).json()
    assert metrics["feedback"] == {"count": 1, "average_rating": 5.0}  # the rejected and forbidden attempts left no trace


@pytest.mark.asyncio
async def test_audit_and_metrics_need_supervisor_role(client) -> None:  # type: ignore[no-untyped-def]
    c, _ = client
    for path in ("/staff/audit", "/staff/metrics"):
        assert (await c.get(path)).status_code == 403
        assert (await c.get(path, headers=bearer(CUSTOMER_ID, "customer"))).status_code == 403
        assert (await c.get(path, headers=bearer(STAFF["agent"], "agent"))).status_code == 403
        assert (await c.get(path, headers=bearer(STAFF["supervisor"], "supervisor"))).status_code == 200

    owner = bearer(CUSTOMER_ID, "customer")
    conv = await new_conversation(c, owner)
    await c.post(f"/conversations/{conv}/feedback", json={"rating": 4}, headers=owner)
    entries = (await c.get("/staff/audit", params={"subject_type": "conversation"}, headers=bearer(STAFF["admin"], "admin"))).json()["entries"]
    assert [e["action"] for e in entries] == ["conversation.feedback"] and entries[0]["after"]["rating"] == 4


@pytest.mark.asyncio
async def test_sandbox_controls_are_admin_only_and_act_on_real_state(client) -> None:  # type: ignore[no-untyped-def]
    c, factory = client
    admin = bearer(STAFF["admin"], "admin")
    async with factory() as session:
        order = OrderModel(
            id=uuid.uuid4(), code="SL-SBX001", customer_id=CUSTOMER_ID, status="shipped", payment_method="card", payment_status="paid",
            subtotal=1, discount_total=0, shipping_fee=0, total=1, paid_amount=1, refunded_amount=0,
        )
        session.add(order)
        await session.flush()
        session.add(ShipmentModel(order_id=order.id, tracking_code="TRK-SBX1", status="shipped"))
        await session.commit()

    path = "/sandbox/shipments/TRK-SBX1/advance"
    assert (await c.post(path, headers=bearer(STAFF["agent"], "agent"))).status_code == 403
    statuses = [(await c.post(path, headers=admin)).json()["status"] for _ in range(3)]
    assert statuses == ["in_transit", "out_for_delivery", "delivered"]
    assert (await c.post(path, headers=admin)).status_code == 409
    assert (await c.post("/sandbox/shipments/NOPE/advance", headers=admin)).status_code == 404

    assert (await c.post("/sandbox/payments/fail-next", json={}, headers=admin)).json() == {"status": "armed"}
    assert get_simulated_gateway()._should_fail_next is True
    get_simulated_gateway().clear_failure()

    frozen = (await c.post("/sandbox/clock", json={"now": "2026-11-11T10:00:00+07:00"}, headers=admin)).json()
    assert frozen["frozen"] and frozen["now"].startswith("2026-11-11T03:00:00")
    assert (await c.post("/sandbox/clock", json={"now": "not a date"}, headers=admin)).status_code == 422
    assert (await c.post("/sandbox/clock", json={}, headers=admin)).json()["frozen"] is False
