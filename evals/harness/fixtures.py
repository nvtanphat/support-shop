"""Insert a scenario's fixture records (staff, customer, orders) into the evaluation database."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from shopagent.core.principal import Principal
from shopagent.domain.models.enums import PaymentStatus
from shopagent.infra.db.tables import (
    CustomerModel,
    OrderItemModel,
    OrderModel,
    ProductModel,
    ProductVariantModel,
    StaffUserModel,
)
from shopagent.rag.indexer import index_policies
from sqlalchemy.ext.asyncio import AsyncSession

from evals.harness.models import Scenario


def _add_staff(session: AsyncSession) -> None:
    session.add(StaffUserModel(id=uuid.UUID(int=1), email="agent@shop.vn", password_hash="pwd", role="agent", full_name="Nhân Viên"))
    session.add(StaffUserModel(id=uuid.UUID(int=2), email="supervisor@shop.vn", password_hash="pwd", role="supervisor", full_name="Trưởng Ca"))


async def _add_customer(session: AsyncSession, principal_spec: dict[str, Any]) -> tuple[Principal, uuid.UUID]:
    """Create the acting customer; a guest acts on an order owned by a different customer."""
    customer_id = uuid.uuid4()
    session.add(
        CustomerModel(
            id=customer_id,
            email=principal_spec.get("email", "eval.customer@example.com"),
            phone=principal_spec.get("phone", "0901234567"),
            full_name=principal_spec.get("full_name", "Khách Đánh Giá"),
            tier=principal_spec.get("tier", "standard"),
        )
    )
    await session.flush()
    if principal_spec.get("type") != "guest":
        return Principal.authenticated_customer(customer_id=customer_id), customer_id

    owner_id = uuid.uuid4()
    session.add(CustomerModel(id=owner_id, email="other.owner@example.com", phone="0988776655", full_name="Chủ Đơn Hàng Khác", tier="standard"))
    await session.flush()
    return Principal.guest(guest_token="guest_token_eval"), owner_id


def _delivery_time(spec: str | None, clock: datetime) -> datetime | None:
    """`-3d` is relative to the scenario clock; anything else is an ISO timestamp."""
    if not spec:
        return None
    if spec.endswith("d"):
        return clock + timedelta(days=float(spec[:-1]))
    return datetime.fromisoformat(spec)


def _add_order_items(session: AsyncSession, order_id: uuid.UUID, item_specs: list[dict[str, Any]]) -> tuple[list[OrderItemModel], int]:
    items: list[OrderItemModel] = []
    subtotal = 0
    for spec in item_specs:
        price, qty = spec["unit_price"], spec["qty"]
        subtotal += price * qty
        product = ProductModel(id=uuid.uuid4(), name=spec.get("key", "Sản phẩm"), category="fashion", return_flags=spec.get("flags", []))
        variant = ProductVariantModel(id=uuid.uuid4(), product_id=product.id, sku=spec["sku"], price=price, stock=50)
        session.add(product)
        session.add(variant)
        items.append(
            OrderItemModel(
                id=uuid.uuid4(),
                order_id=order_id,
                variant_id=variant.id,
                qty=qty,
                unit_price=price,
                allocated_discount=0,
                returned_qty=0,
                exchanged=False,
            )
        )
    return items, subtotal


def _add_order(session: AsyncSession, spec: dict[str, Any], owner_id: uuid.UUID, clock: datetime) -> OrderModel:
    order_id = uuid.uuid4()
    delivered_at = _delivery_time(spec.get("delivered_at"), clock)
    placed_at = (delivered_at - timedelta(days=2)) if delivered_at else (clock - timedelta(days=1))
    items, subtotal = _add_order_items(session, order_id, spec.get("items", []))

    discount_total = spec.get("discount_total", 0)
    shipping_fee = spec.get("shipping_fee", 0)
    total = subtotal - discount_total + shipping_fee
    for item in items:  # spread the order discount across lines in proportion to their value
        item.allocated_discount = int(item.unit_price * item.qty * discount_total / subtotal) if subtotal > 0 else 0
        session.add(item)

    paid = spec.get("status") == "delivered"
    order = OrderModel(
        id=order_id,
        code=spec["code"],
        customer_id=owner_id,
        status=spec.get("status", "delivered"),
        payment_method=spec.get("payment_method", "card"),
        payment_status=PaymentStatus.PAID.value if paid else PaymentStatus.UNPAID.value,
        subtotal=subtotal,
        discount_total=discount_total,
        shipping_fee=shipping_fee,
        total=total,
        paid_amount=total if paid else 0,
        refunded_amount=0,
        channel="web",
        policy_version="2026-11-01",
        placed_at=placed_at,
        delivered_at=delivered_at,
    )
    session.add(order)
    return order


async def setup_scenario_fixtures(
    session: AsyncSession,
    scenario: Scenario,
    clock_dt: datetime,
) -> tuple[Principal, list[OrderModel]]:
    """Index the policies and insert the scenario's staff, customer and orders."""
    await index_policies(session)
    _add_staff(session)
    principal, owner_id = await _add_customer(session, scenario.principal)
    orders = [_add_order(session, spec, owner_id, clock_dt) for spec in scenario.fixtures.get("orders", [])]
    await session.commit()
    return principal, orders
