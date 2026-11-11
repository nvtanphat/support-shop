"""SQLAlchemy 2.0 Table and ORM Model definitions."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    JSON,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from shopagent.core.ids import generate_uuid


class Base(DeclarativeBase):
    pass


class CustomerModel(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    credentials = relationship("CustomerCredentialsModel", back_populates="customer", uselist=False)
    orders = relationship("OrderModel", back_populates="customer")


class CustomerCredentialsModel(Base):
    __tablename__ = "customer_credentials"

    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    customer = relationship("CustomerModel", back_populates="credentials")


class StaffUserModel(Base):
    __tablename__ = "staff_users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # agent, supervisor, admin
    full_name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ProductModel(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    return_flags: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)  # final_sale, hygiene, sealed_cosmetic, personalized
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    variants = relationship("ProductVariantModel", back_populates="product")


class ProductVariantModel(Base):
    __tablename__ = "product_variants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0)

    product = relationship("ProductModel", back_populates="variants")


class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(32), nullable=False)
    subtotal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_total: Mapped[int] = mapped_column(BigInteger, default=0)
    shipping_fee: Mapped[int] = mapped_column(BigInteger, default=0)
    total: Mapped[int] = mapped_column(BigInteger, nullable=False)
    paid_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    refunded_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    channel: Mapped[str] = mapped_column(String(32), default="web")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_version: Mapped[str] = mapped_column(String(32), default="2026-11-01")
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    customer = relationship("CustomerModel", back_populates="orders")
    items = relationship("OrderItemModel", back_populates="order", cascade="all, delete-orphan")
    returns = relationship("ReturnRequestModel", back_populates="order")
    refunds = relationship("RefundModel", back_populates="order")


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("product_variants.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocated_discount: Mapped[int] = mapped_column(BigInteger, default=0)
    returned_qty: Mapped[int] = mapped_column(Integer, default=0)
    exchanged: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        CheckConstraint("returned_qty <= qty", name="check_returned_qty_le_qty"),
    )

    order = relationship("OrderModel", back_populates="items")
    variant = relationship("ProductVariantModel")


class PaymentModel(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"), index=True)
    gateway: Mapped[str] = mapped_column(String(32), nullable=False)
    gateway_txn_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="simulated")  # simulated, sandbox
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("gateway", "gateway_txn_id", name="uq_gateway_txn"),
    )


class ShipmentModel(Base):
    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"), index=True)
    carrier: Mapped[str] = mapped_column(String(64), default="ShopLab Logistics")
    tracking_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="shipped")
    direction: Mapped[str] = mapped_column(String(16), default="outbound")  # outbound, return
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    events = relationship("ShipmentEventModel", back_populates="shipment", cascade="all, delete-orphan")


class ShipmentEventModel(Base):
    __tablename__ = "shipment_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    shipment_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shipments.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    location: Mapped[str] = mapped_column(String(255), default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    shipment = relationship("ShipmentModel", back_populates="events")


class ReturnRequestModel(Base):
    __tablename__ = "return_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id"), index=True)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    resolution: Mapped[str] = mapped_column(String(16), nullable=False)  # refund, exchange
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    risk_flags: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    policy_version: Mapped[str] = mapped_column(String(32), default="2026-11-01")
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deadline_ship_back: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    order = relationship("OrderModel", back_populates="returns")
    items = relationship("ReturnItemModel", back_populates="return_request", cascade="all, delete-orphan")
    evidence_files = relationship("EvidenceFileModel", back_populates="return_request", cascade="all, delete-orphan")


class ReturnItemModel(Base):
    __tablename__ = "return_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    return_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("return_requests.id", ondelete="CASCADE"), index=True)
    order_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("order_items.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    inspection_result: Mapped[str] = mapped_column(String(32), default="pending")

    return_request = relationship("ReturnRequestModel", back_populates="items")
    order_item = relationship("OrderItemModel")


class EvidenceFileModel(Base):
    __tablename__ = "evidence_files"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    return_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("return_requests.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="photo")  # photo, video
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(64), default="customer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    return_request = relationship("ReturnRequestModel", back_populates="evidence_files")


class RefundModel(Base):
    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"), index=True)
    return_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("return_requests.id"), nullable=True, index=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    method: Mapped[str] = mapped_column(String(32), default="original")
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    gateway_txn_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    order = relationship("OrderModel", back_populates="refunds")


class ExchangeModel(Base):
    __tablename__ = "exchanges"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    return_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("return_requests.id"), index=True)
    new_variant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("product_variants.id"), index=True)
    new_shipment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("shipments.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ApprovalRequestModel(Base):
    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # return_request, refund, cancellation
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    gate: Mapped[str] = mapped_column(String(32), nullable=False)  # A_return, B_refund, cancel_packing
    required_role: Mapped[str] = mapped_column(String(32), default="agent")  # agent, supervisor
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("staff_users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PendingActionModel(Base):
    __tablename__ = "pending_actions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    preview: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    presented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)

    __table_args__ = (
        Index("idx_pending_action_uniq", "conversation_id", "payload_hash", unique=True, postgresql_where=(Column("status") == "proposed")),
    )


class TicketModel(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    assignee: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("staff_users.id"), nullable=True)
    agent_summary: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class GuestVerificationModel(Base):
    __tablename__ = "guest_verifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    guest_token: Mapped[str] = mapped_column(String(64), index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    phone_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grant_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ConversationModel(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    guest_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(32), default="ai", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    last_event_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("MessageModel", back_populates="conversation", cascade="all, delete-orphan")


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # customer, assistant, staff, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    author_staff_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    conversation = relationship("ConversationModel", back_populates="messages")


class ConversationEventModel(Base):
    __tablename__ = "conversation_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_conv_seq"),
    )


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)  # customer, staff, system, agent
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class IdempotencyKeyModel(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), default="api")
    response_digest: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class PolicyDocumentModel(Base):
    __tablename__ = "policy_documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class PolicyChunkModel(Base):
    __tablename__ = "policy_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("policy_documents.id", ondelete="CASCADE"), index=True)
    clause_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category_scope: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_unaccent: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(JSON_TYPE, default=list)  # Stored as JSONB or vector
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
