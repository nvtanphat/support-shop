"""Order codes cannot be probed: another customer's order looks exactly like a missing one."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from shopagent.api.app import app
from shopagent.api.deps import get_db_session
from shopagent.core.security import hash_password
from shopagent.infra.db.tables import Base, CustomerCredentialsModel, CustomerModel, OrderModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    owner, intruder = uuid.uuid4(), uuid.uuid4()
    async with factory() as session:
        for cid, email, phone in ((owner, "owner@example.com", "0900000001"), (intruder, "intruder@example.com", "0900000002")):
            session.add(CustomerModel(id=cid, email=email, phone=phone, full_name="K"))
            session.add(CustomerCredentialsModel(customer_id=cid, password_hash=hash_password("Pass1234!")))
        session.add(
            OrderModel(
                id=uuid.uuid4(), customer_id=owner, code="SL-PRIV01", status="delivered", payment_method="cod",
                payment_status="paid", subtotal=100000, total=100000,
            )
        )
        await session.commit()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def login(client: AsyncClient, email: str) -> dict[str, str]:
    res = await client.post("/auth/login", json={"email": email, "password": "Pass1234!"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.mark.asyncio
async def test_signed_in_customer_cannot_tell_foreign_order_from_missing(client: AsyncClient) -> None:
    headers = await login(client, "intruder@example.com")
    for path in ("/orders/{}", "/me/orders/{}"):
        foreign = await client.get(path.format("SL-PRIV01"), headers=headers)
        missing = await client.get(path.format("SL-NOPE99"), headers=headers)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()
    owner = await client.get("/orders/SL-PRIV01", headers=await login(client, "owner@example.com"))
    assert owner.status_code == 200 and owner.json()["order_code"] == "SL-PRIV01"


@pytest.mark.asyncio
async def test_unverified_guest_gets_the_same_answer_for_any_code(client: AsyncClient) -> None:
    existing = await client.get("/orders/SL-PRIV01")
    unknown = await client.get("/orders/SL-NOPE99")
    assert existing.status_code == unknown.status_code == 403
    assert existing.json() == unknown.json()
