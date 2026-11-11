"""Simulated payment gateway adapter with fault injection support."""

from __future__ import annotations

import secrets
from typing import Any

from shopagent.infra.payments.port import PaymentGatewayPort, PaymentResult


class SimulatedPaymentGateway(PaymentGatewayPort):
    def __init__(self) -> None:
        self._should_fail_next = False
        self._fail_error_message = "Simulated payment gateway timeout"
        self._transactions: dict[str, PaymentResult] = {}

    @property
    def mode(self) -> str:
        return "simulated"

    def inject_failure_next(self, message: str = "Simulated payment failure") -> None:
        self._should_fail_next = True
        self._fail_error_message = message

    def clear_failure(self) -> None:
        self._should_fail_next = False

    async def refund(
        self,
        refund_code: str,
        original_txn_id: str,
        amount: int,
        reason: str,
        idempotency_key: str,
    ) -> PaymentResult:
        if self._should_fail_next:
            self._should_fail_next = False
            return PaymentResult(
                success=False,
                gateway_txn_id="",
                status="failed",
                amount=amount,
                raw_response={"simulated_error": True},
                error_message=self._fail_error_message,
            )

        # Check idempotency
        if idempotency_key in self._transactions:
            return self._transactions[idempotency_key]

        sim_txn_id = f"SIM-RF-{secrets.token_hex(6).upper()}"
        result = PaymentResult(
            success=True,
            gateway_txn_id=sim_txn_id,
            status="succeeded",
            amount=amount,
            raw_response={
                "gateway": "simulated",
                "refund_code": refund_code,
                "original_txn_id": original_txn_id,
                "amount": amount,
                "reason": reason,
            },
        )
        self._transactions[idempotency_key] = result
        self._transactions[sim_txn_id] = result
        return result

    async def query_transaction(self, gateway_txn_id: str) -> PaymentResult:
        if gateway_txn_id in self._transactions:
            return self._transactions[gateway_txn_id]
        return PaymentResult(
            success=False,
            gateway_txn_id=gateway_txn_id,
            status="not_found",
            amount=0,
            raw_response={},
            error_message="Giao dịch không tồn tại",
        )
