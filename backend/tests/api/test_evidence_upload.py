"""Return evidence upload: several files at once, type and size checks, ownership."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from shopagent.api.app import app
from shopagent.api.deps import get_db_session
from shopagent.api.routers import actions
from shopagent.core.security import create_access_token
from shopagent.infra.db.tables import (
    Base,
    CustomerModel,
    EvidenceFileModel,
    OrderModel,
    ReturnRequestModel,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

OWNER, STRANGER = uuid.uuid4(), uuid.uuid4()


def auth(customer_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(customer_id), 'email': 'x@example.com', 'role': 'customer'})}"}


@pytest.fixture
async def env(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(actions, "_UPLOAD_DIR", tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        session.add(CustomerModel(id=OWNER, email="o@example.com", phone="0901111111", full_name="Chủ"))
        session.add(CustomerModel(id=STRANGER, email="s@example.com", phone="0902222222", full_name="Khác"))
        order = OrderModel(
            id=uuid.uuid4(), code="SL-EVD900", customer_id=OWNER, status="delivered", payment_method="card", payment_status="paid",
            subtotal=1, discount_total=0, shipping_fee=0, total=1, paid_amount=1, refunded_amount=0,
        )
        session.add(order)
        await session.flush()
        session.add(ReturnRequestModel(id=uuid.uuid4(), code="RT-EVD900", order_id=order.id, customer_id=OWNER, reason_code="defective", resolution="refund", status="pending_evidence"))
        await session.commit()

    async def override():  # type: ignore[no-untyped-def]
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory, tmp_path
    app.dependency_overrides.clear()
    await engine.dispose()


def png(name: str = "a.png", payload: bytes = b"\x89PNG-1") -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, payload, "image/png"))


@pytest.mark.asyncio
async def test_owner_uploads_several_files_in_one_request(env) -> None:  # type: ignore[no-untyped-def]
    client, factory, folder = env
    resp = await client.post(
        "/returns/RT-EVD900/evidence",
        files=[png("a.png", b"one"), png("b.png", b"two"), ("files", ("c.mp4", b"video", "video/mp4"))],
        headers=auth(OWNER),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["uploaded_count"] == 3
    assert sorted(f["kind"] for f in resp.json()["files"]) == ["photo", "photo", "video"]
    assert len(list(folder.iterdir())) == 3
    async with factory() as session:
        assert len((await session.execute(select(EvidenceFileModel))).scalars().all()) == 3


@pytest.mark.asyncio
async def test_one_bad_file_rejects_the_whole_upload_and_stores_nothing(env) -> None:  # type: ignore[no-untyped-def]
    client, factory, folder = env
    resp = await client.post(
        "/returns/RT-EVD900/evidence",
        files=[png("ok.png"), ("files", ("run.exe", b"MZ", "application/octet-stream"))],
        headers=auth(OWNER),
    )
    assert resp.status_code == 422 and ".exe" in resp.json()["detail"]
    assert list(folder.iterdir()) == []
    async with factory() as session:
        assert (await session.execute(select(EvidenceFileModel))).scalars().all() == []


@pytest.mark.asyncio
async def test_oversized_file_and_too_many_files_are_refused(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, _, folder = env
    monkeypatch.setattr(actions, "_MAX_EVIDENCE_BYTES", 10)
    big = await client.post("/returns/RT-EVD900/evidence", files=[png("big.png", b"x" * 11)], headers=auth(OWNER))
    assert big.status_code == 413
    many = await client.post("/returns/RT-EVD900/evidence", files=[png(f"{i}.png", bytes([i])) for i in range(7)], headers=auth(OWNER))
    assert many.status_code == 422
    assert list(folder.iterdir()) == []


@pytest.mark.asyncio
async def test_only_the_owner_can_upload_and_unknown_returns_are_404(env) -> None:  # type: ignore[no-untyped-def]
    client, _, folder = env
    assert (await client.post("/returns/RT-EVD900/evidence", files=[png()], headers=auth(STRANGER))).status_code == 403
    assert (await client.post("/returns/RT-NOPE00/evidence", files=[png()], headers=auth(OWNER))).status_code == 404
    assert (await client.post("/returns/RT-EVD900/evidence", files=[png()])).status_code == 401
    assert list(folder.iterdir()) == []
