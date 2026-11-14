"""Payment gateway port interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class PaymentResult:
    success: bool
    gateway_txn_id: str
    status: str
    amount: int
    raw_response: dict[str, Any]
    error_message: str | None = None


class PaymentGatewayPort(ABC):
    @property
    @abstractmethod
    def mode(self) -> str:
        """Return mode: simulated, sandbox, or real."""
        pass

    @abstractmethod
    async def refund(
        self,
        refund_code: str,
        original_txn_id: str,
        amount: int,
        reason: str,
        idempotency_key: str,
    ) -> PaymentResult:
        """Process refund to customer via payment gateway."""
        pass

    @abstractmethod
    async def query_transaction(self, gateway_txn_id: str) -> PaymentResult:
        """Query status of a transaction for reconciliation."""
        pass
