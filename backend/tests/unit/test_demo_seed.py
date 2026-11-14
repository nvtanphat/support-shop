"""The curated demo cases behave the way their notes say, under the real policy engine and API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from shopagent.api.app import app
from shopagent.api.deps import get_db_session
from shopagent.core.clock import Clock, get_clock, set_global_clock
from shopagent.core.principal import Principal
from shopagent.domain.seeder import generate_seed_data
from shopagent.domain.services.returns import ReturnService
from shopagent.infra.db.repositories.order_repo import OrderRepository
from shopagent.infra.db.tables import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


@pytest.fixture
async def seeded():  # type: ignore[no-untyped-def]
    previous = get_clock()
    set_global_clock(Clock(fixed_now=NOW))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        await generate_seed_data(session, now=NOW, num_customers=10, num_products=10, num_orders=40)
    yield factory
    await engine.dispose()
    set_global_clock(previous)


async def _check(factory: Any, order_code: str, reason: str, customer_no: int = 1) -> dict[str, Any]:
    import uuid

    async with factory() as session:
        order = await OrderRepository(session).get_by_code(order_code)
        item_ids = [str(i.id) for i in order.items]
        principal = Principal.customer(uuid.UUID(int=1000 + customer_no))
        return await ReturnService(session).check_eligibility_for_principal(principal, order_code, item_ids, reason)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("order", "reason", "eligible"),
    [
        ("SL-DEMO06", "change_of_mind", True),   # delivered 2 days ago
        ("SL-DEMO07", "change_of_mind", False),  # 10 days: past the 7-day window
        ("SL-DEMO07", "defective", True),        # 10 days: inside the 15-day defect window
        ("SL-DEMO08", "defective", False),       # 20 days: past every window
        ("SL-DEMO09", "change_of_mind", False),  # sealed cosmetic + hygiene excluded
        ("SL-DEMO10", "change_of_mind", False),  # final sale
    ],
)
async def test_return_windows_and_exclusions(seeded: Any, order: str, reason: str, eligible: bool) -> None:
    result = await _check(seeded, order, reason)
    assert result["eligible"] is eligible, result["message"]


@pytest.mark.asyncio
async def test_defect_on_expensive_phone_needs_evidence(seeded: Any) -> None:
    result = await _check(seeded, "SL-DEMO11", "defective")
    assert result["eligible"] and result["requires_evidence"]
    assert result["estimated_refund"]["amount"] > 2_000_000  # supervisor territory


@pytest.mark.asyncio
async def test_staff_see_the_seeded_queues(seeded: Any) -> None:
    async def override():  # type: ignore[no-untyped-def]
        async with seeded() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            login = await c.post("/staff/auth/login", json={"email": "supervisor@shop.vn", "password": "staff123"})
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            approvals = (await c.get("/staff/approvals?status=pending", headers=headers)).json()["approvals"]
            assert {a["gate"] for a in approvals} == {"A_return", "B_refund"}
            returns = (await c.get("/staff/returns", headers=headers)).json()["returns"]
            by_code = {r["code"]: r for r in returns}
            assert by_code["RT-DEMO15"]["status"] == "awaiting_return"
            assert by_code["RT-DEMO16"]["status"] == "received" and by_code["RT-DEMO16"]["evidence_count"] == 3
            tickets = (await c.get("/staff/tickets", headers=headers)).json()["tickets"]
            assert [t["code"] for t in tickets] == ["TK-DEMO01"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_risk_flags_for_demo_accounts(seeded: Any) -> None:
    import uuid
    from datetime import timedelta

    from shopagent.core.config import get_rules_config
    from shopagent.domain.policies.risk import evaluate_risk_flags
    from shopagent.infra.db.tables import CustomerModel, OrderModel, ReturnRequestModel
    from sqlalchemy import func, select

    cfg = get_rules_config()["risk_flags"]
    async with seeded() as session:
        async def flags(customer_no: int, order_code: str) -> list[str]:
            cid = uuid.UUID(int=1000 + customer_no)
            cust = await session.get(CustomerModel, cid)
            order = (await session.execute(select(OrderModel).where(OrderModel.code == order_code))).scalar_one()
            recent = (
                await session.execute(
                    select(func.count()).select_from(ReturnRequestModel).where(
                        ReturnRequestModel.customer_id == cid, ReturnRequestModel.created_at >= NOW - timedelta(days=30)
                    )
                )
            ).scalar_one()
            created = cust.created_at.replace(tzinfo=NOW.tzinfo)  # SQLite drops the offset
            return evaluate_risk_flags(created, order.total, recent, 0, 0, NOW, cfg)

        assert await flags(2, "SL-DEMO19") == ["new_account_high_value"]
        assert "many_returns" in await flags(3, "SL-DEMO20")
        assert await flags(1, "SL-DEMO06") == []
