"""Domain entity dataclasses and models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from shopagent.domain.models.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ProductCategory,
    ReturnFlag,
)


@dataclass
class OrderItem:
    id: uuid.UUID
    order_id: uuid.UUID
    variant_id: uuid.UUID
    qty: int
    unit_price: int
    allocated_discount: int = 0
    returned_qty: int = 0
    exchanged: bool = False
    sku: str = ""
    product_name: str = ""
    category: ProductCategory = ProductCategory.FASHION
    return_flags: list[ReturnFlag] = field(default_factory=list)

    @property
    def remaining_returnable_qty(self) -> int:
        return max(0, self.qty - self.returned_qty)


@dataclass
class Order:
    id: uuid.UUID
    code: str
    customer_id: uuid.UUID
    status: OrderStatus
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    subtotal: int
    discount_total: int
    shipping_fee: int
    total: int
    paid_amount: int = 0
    refunded_amount: int = 0
    channel: str = "web"  # web, marketplace
    note: str | None = None
    policy_version: str = "2026-11-01"
    placed_at: datetime | None = None
    delivered_at: datetime | None = None
    items: list[OrderItem] = field(default_factory=list)
