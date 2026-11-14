"""Policy data structures matching rules.yaml schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReturnWindowRules(BaseModel):
    defect_like: int = 15
    change_of_mind: int = 7


class ReturnEvidenceRules(BaseModel):
    required_for: list[str] = Field(default_factory=lambda: [
        "defective", "damaged_in_transit", "wrong_item", "missing_item", "not_as_described"
    ])
    min_photos: int = 2
    video_required_for: list[str] = Field(default_factory=lambda: ["missing_item"])


class ReturnShippingRules(BaseModel):
    shop_fault_reasons: list[str] = Field(default_factory=lambda: [
        "defective", "damaged_in_transit", "wrong_item", "missing_item", "not_as_described"
    ])
    customer_fee_vnd: int = 30000


class ReturnPolicyRules(BaseModel):
    windows_days: ReturnWindowRules = Field(default_factory=ReturnWindowRules)
    change_of_mind_excluded_flags: list[str] = Field(default_factory=lambda: [
        "final_sale", "hygiene", "sealed_cosmetic", "personalized"
    ])
    evidence: ReturnEvidenceRules = Field(default_factory=ReturnEvidenceRules)
    return_shipping: ReturnShippingRules = Field(default_factory=ReturnShippingRules)
    ship_back_deadline_days: int = 5
    deadline_rule: str = "end_of_local_day"


class RefundSlaRules(BaseModel):
    ewallet: list[int] = Field(default_factory=lambda: [1, 3])
    bank_transfer: list[int] = Field(default_factory=lambda: [3, 5])
    card: list[int] = Field(default_factory=lambda: [7, 15])


class RefundPolicyRules(BaseModel):
    auto_approve_max_vnd: int = 500000
    agent_approve_max_vnd: int = 2000000
    sla_working_days: RefundSlaRules = Field(default_factory=RefundSlaRules)


class CancelPolicyRules(BaseModel):
    self_service_statuses: list[str] = Field(default_factory=lambda: ["pending_payment", "confirmed"])
    needs_approval_statuses: list[str] = Field(default_factory=lambda: ["packing"])


class ExchangePolicyRules(BaseModel):
    same_product_only: bool = True
    same_price_only: bool = True
    max_times_per_item: int = 1


class RiskFlagRules(BaseModel):
    many_returns: dict[str, Any] = Field(default_factory=lambda: {"count": 3, "window_days": 30})
    high_return_rate: dict[str, Any] = Field(default_factory=lambda: {"ratio": 0.5, "last_orders": 10})
    new_account_high_value: dict[str, Any] = Field(default_factory=lambda: {"account_age_days": 7, "order_total_vnd": 2000000})


class PolicyRules(BaseModel):
    version: str = "2026-11-01"
    effective_from: str = "2026-11-01T00:00:00+07:00"
    effective_to: str | None = None
    timezone: str = "Asia/Ho_Chi_Minh"
    return_policy: ReturnPolicyRules = Field(default_factory=ReturnPolicyRules, alias="return")
    refund_policy: RefundPolicyRules = Field(default_factory=RefundPolicyRules, alias="refund")
    cancel_policy: CancelPolicyRules = Field(default_factory=CancelPolicyRules, alias="cancel")
    exchange_policy: ExchangePolicyRules = Field(default_factory=ExchangePolicyRules, alias="exchange")
    risk_flags: RiskFlagRules = Field(default_factory=RiskFlagRules)
    pending_action_ttl_minutes: int = 30
