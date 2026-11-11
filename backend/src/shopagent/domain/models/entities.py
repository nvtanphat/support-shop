"""Domain entity dataclasses and models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid

from shopagent.domain.models.enums import (
    ApprovalGate,
    ApprovalStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    PendingActionStatus,
    PendingActionType,
    ProductCategory,
    RefundStatus,
    ReturnFlag,
    ReturnReason,
    ReturnResolution,
    ReturnStatus,
)


@dataclass
class Customer:
    id: uuid.UUID
    email: str
    phone: str
    full_name: str
    tier: str = "standard"  # standard, silver, gold, diamond
    created_at: datetime | None = None


@dataclass
class StaffUser:
    id: uuid.UUID
    email: str
    password_hash: str
    role: str  # agent, supervisor, admin
    full_name: str = ""


@dataclass
class Product:
    id: uuid.UUID
    name: str
    category: ProductCategory
    return_flags: list[ReturnFlag] = field(default_factory=list)


@dataclass
class ProductVariant:
    id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    attributes: dict[str, str] = field(default_factory=dict)
    price: int = 0
    stock: int = 0


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


@dataclass
class ReturnItem:
    id: uuid.UUID
    return_id: uuid.UUID
    order_item_id: uuid.UUID
    qty: int
    inspection_result: str = "pending"  # accepted, rejected, partial


@dataclass
class ReturnRequest:
    id: uuid.UUID
    code: str
    order_id: uuid.UUID
    customer_id: uuid.UUID
    reason_code: ReturnReason
    resolution: ReturnResolution
    status: ReturnStatus
    risk_flags: list[str] = field(default_factory=list)
    policy_version: str = "2026-11-01"
    decided_by: str | None = None
    deadline_ship_back: datetime | None = None
    items: list[ReturnItem] = field(default_factory=list)
    created_at: datetime | None = None


@dataclass
class Refund:
    id: uuid.UUID
    code: str
    order_id: uuid.UUID
    return_id: uuid.UUID | None
    amount: int
    breakdown: dict[str, Any] = field(default_factory=dict)
    method: str = "original"
    status: RefundStatus = RefundStatus.CREATED
    gateway_txn_id: str | None = None
    attempts: int = 0
    created_at: datetime | None = None


@dataclass
class ApprovalRequest:
    id: uuid.UUID
    subject_type: str  # return_request, refund, cancellation
    subject_id: uuid.UUID
    gate: ApprovalGate
    required_role: str  # agent, supervisor
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime | None = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    note: str | None = None


@dataclass
class PendingAction:
    id: uuid.UUID
    conversation_id: uuid.UUID
    customer_id: uuid.UUID
    type: PendingActionType
    payload: dict[str, Any]
    payload_hash: str
    preview: dict[str, Any]
    status: PendingActionStatus = PendingActionStatus.PROPOSED
    presented_at: datetime | None = None
    expires_at: datetime | None = None
    result: dict[str, Any] = field(default_factory=dict)
