"""Risk flag evaluation based on deterministic business rules."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def evaluate_risk_flags(
    customer_created_at: datetime | None,
    order_total: int,
    recent_return_count_30d: int,
    recent_orders_count: int,
    recent_returned_orders_count: int,
    now: datetime,
    risk_config: dict[str, Any] | None = None,
) -> list[str]:
    """Evaluate deterministic risk flags for a customer request.

    Returns a list of triggered risk flag keys.
    """
    flags: list[str] = []
    cfg = risk_config or {}

    many_ret_cfg = cfg.get("many_returns", {"count": 3, "window_days": 30})
    if recent_return_count_30d >= many_ret_cfg.get("count", 3):
        flags.append("many_returns")

    ratio_cfg = cfg.get("high_return_rate", {"ratio": 0.5, "last_orders": 10})
    if recent_orders_count >= 3:
        rate = recent_returned_orders_count / recent_orders_count
        if rate > ratio_cfg.get("ratio", 0.5):
            flags.append("high_return_rate")

    new_acc_cfg = cfg.get("new_account_high_value", {"account_age_days": 7, "order_total_vnd": 2000000})
    if customer_created_at is not None:
        age_days = (now - customer_created_at).total_seconds() / 86400.0
        if age_days < new_acc_cfg.get("account_age_days", 7) and order_total > new_acc_cfg.get("order_total_vnd", 2000000):
            flags.append("new_account_high_value")

    return flags
