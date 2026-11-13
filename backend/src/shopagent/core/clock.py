"""Injectable clock and timezone-aware deadline computation."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

STORE_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def get_shop_timezone() -> ZoneInfo:
    return STORE_TIMEZONE


class Clock:
    """An injectable clock that supports fixed time for tests and evals."""

    def __init__(self, fixed_now: datetime | None = None) -> None:
        self._fixed_now = fixed_now

    def now(self) -> datetime:
        """Return current datetime in UTC (with timezone)."""
        if self._fixed_now is not None:
            if self._fixed_now.tzinfo is None:
                return self._fixed_now.replace(tzinfo=STORE_TIMEZONE).astimezone(ZoneInfo("UTC"))
            return self._fixed_now.astimezone(ZoneInfo("UTC"))
        return datetime.now(ZoneInfo("UTC"))

    def set_fixed_now(self, dt: datetime | None) -> None:
        """Update or reset fixed datetime."""
        self._fixed_now = dt


# Global default clock instance (can be overridden in tests/harness)
_default_clock = Clock()


def get_clock() -> Clock:
    return _default_clock


def to_utc(dt: datetime) -> datetime:
    """Normalize datetime to UTC-aware datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("UTC"))


def set_global_clock(clock: Clock) -> None:
    global _default_clock
    _default_clock = clock


def compute_deadline_days_end_of_day(start_dt: datetime, days: int) -> datetime:
    """Hạn chót là 23:59:59 theo giờ cửa hàng của ngày (ngày giao tính theo giờ cửa hàng + N).

    Ví dụ: giao lúc 23:30 ngày 01/11 giờ VN (16:30 UTC), hạn 7 ngày là
    23:59:59 ngày 08/11 giờ VN.
    Kết quả trả về dạng UTC timezone-aware.
    """
    if start_dt.tzinfo is None:
        start_local = start_dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(STORE_TIMEZONE)
    else:
        start_local = start_dt.astimezone(STORE_TIMEZONE)

    target_date: date = start_local.date() + timedelta(days=days)
    end_of_day_local = datetime.combine(
        target_date, time(23, 59, 59, 999999), tzinfo=STORE_TIMEZONE
    )
    return end_of_day_local.astimezone(ZoneInfo("UTC"))
