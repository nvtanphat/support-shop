"""Principal representing the authenticated caller identity and permissions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import uuid


class PrincipalRole(str, Enum):
    GUEST = "guest"
    CUSTOMER = "customer"
    STAFF_AGENT = "agent"
    STAFF_SUPERVISOR = "supervisor"
    STAFF_ADMIN = "admin"
    AGENT = "agent"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"
    SYSTEM = "system"


@dataclass(frozen=True)
class Principal:
    """Authenticated caller identity."""

    role: PrincipalRole
    customer_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None
    guest_token: str | None = None
    # For guests who verified ownership of a single order via OTP
    verified_order_id: uuid.UUID | None = None
    permissions: set[str] = field(default_factory=set)

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.staff_id if self.is_staff else self.customer_id

    @classmethod
    def authenticated_customer(cls, customer_id: uuid.UUID, email: str = "") -> Principal:
        return cls(role=PrincipalRole.CUSTOMER, customer_id=customer_id)

    @classmethod
    def customer(cls, customer_id: uuid.UUID, email: str = "") -> Principal:
        return cls(role=PrincipalRole.CUSTOMER, customer_id=customer_id)

    @classmethod
    def staff(
        cls,
        staff_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        email: str = "",
        role: PrincipalRole = PrincipalRole.STAFF_AGENT,
    ) -> Principal:
        sid = staff_id or user_id
        return cls(role=role, staff_id=sid)

    @classmethod
    def guest(cls, guest_token: str | None = None, verified_order_id: uuid.UUID | None = None) -> Principal:
        return cls(role=PrincipalRole.GUEST, guest_token=guest_token, verified_order_id=verified_order_id)

    @property
    def is_authenticated_customer(self) -> bool:
        return self.role == PrincipalRole.CUSTOMER and self.customer_id is not None

    @property
    def is_guest(self) -> bool:
        return self.role == PrincipalRole.GUEST

    @property
    def is_staff(self) -> bool:
        return self.role in {
            PrincipalRole.STAFF_AGENT,
            PrincipalRole.STAFF_SUPERVISOR,
            PrincipalRole.STAFF_ADMIN,
        }

    @property
    def is_supervisor_or_admin(self) -> bool:
        return self.role in {PrincipalRole.STAFF_SUPERVISOR, PrincipalRole.STAFF_ADMIN}

    @property
    def is_admin(self) -> bool:
        return self.role == PrincipalRole.STAFF_ADMIN

    @property
    def is_system(self) -> bool:
        return self.role == PrincipalRole.SYSTEM

    def can_access_order(self, order_customer_id: uuid.UUID | None, order_id: uuid.UUID) -> bool:
        """Check if this principal can view or act on an order."""
        if self.is_system or self.is_staff:
            return True
        if self.is_authenticated_customer and order_customer_id is not None:
            return self.customer_id == order_customer_id
        if self.is_guest:
            return self.verified_order_id is not None and self.verified_order_id == order_id
        return False
