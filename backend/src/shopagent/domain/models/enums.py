"""Domain enumeration types."""

from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    PAID = "confirmed"
    PACKING = "packing"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERY_FAILED = "delivery_failed"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RETURNING_TO_SELLER = "returning_to_seller"
    RETURNED_TO_SELLER = "returned_to_seller"
    RETURN_REQUESTED = "returning_to_seller"
    RETURNED = "returned_to_seller"
    PARTIALLY_RETURNED = "delivered"


class PaymentMethod(StrEnum):
    COD = "cod"
    BANK_TRANSFER = "bank_transfer"
    EWALLET = "ewallet"
    CARD = "card"


class PaymentStatus(StrEnum):
    UNPAID = "unpaid"
    PAID = "paid"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"


class ReturnReason(StrEnum):
    DEFECTIVE = "defective"
    DAMAGED_IN_TRANSIT = "damaged_in_transit"
    WRONG_ITEM = "wrong_item"
    MISSING_ITEM = "missing_item"
    NOT_AS_DESCRIBED = "not_as_described"
    CHANGE_OF_MIND = "change_of_mind"


class ReturnResolution(StrEnum):
    REFUND = "refund"
    EXCHANGE = "exchange"


class ReturnStatus(StrEnum):
    REQUESTED = "requested"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    AWAITING_RETURN = "awaiting_return"
    IN_TRANSIT_BACK = "in_transit_back"
    RECEIVED = "received"
    INSPECTING = "inspecting"
    ACCEPTED = "accepted"
    COMPLETED = "accepted"
    PARTIALLY_ACCEPTED = "partially_accepted"
    REJECTED_AFTER_INSPECTION = "rejected_after_inspection"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CLOSED = "closed"


class RefundStatus(StrEnum):
    CREATED = "created"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class ApprovalGate(StrEnum):
    A_RETURN = "A_return"
    B_REFUND = "B_refund"
    CANCEL_PACKING = "cancel_packing"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PendingActionType(StrEnum):
    CANCEL_ORDER = "cancel_order"
    RETURN_REQUEST = "return_request"


class PendingActionStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


class TicketPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ConversationMode(StrEnum):
    AI = "ai"
    WAITING_HUMAN = "waiting_human"
    HUMAN = "human"
    CLOSED = "closed"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"


class ProductCategory(StrEnum):
    FASHION = "fashion"
    APPAREL = "fashion"
    FOOTWEAR = "fashion"
    ELECTRONICS_ACCESSORIES = "electronics_accessories"
    ELECTRONICS = "electronics_accessories"
    COSMETICS = "cosmetics"
    HOME_LIVING = "home_living"
    UNDERGARMENTS = "fashion"
    ACCESSORIES = "electronics_accessories"
    FOOD_PERISHABLE = "home_living"


class ReturnFlag(StrEnum):
    FINAL_SALE = "final_sale"
    HYGIENE = "hygiene"
    SEALED_COSMETIC = "sealed_cosmetic"
    PERSONALIZED = "personalized"
    PERISHABLE = "final_sale"
