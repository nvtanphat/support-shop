"""OTP and SMS port and simulated SMS adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SentSMS:
    phone: str
    message: str
    otp_code: str
    sent_at: datetime


class SmsPort(ABC):
    @abstractmethod
    async def send_otp(self, phone: str, otp_code: str) -> bool:
        pass


class SimulatedSmsAdapter(SmsPort):
    def __init__(self) -> None:
        self.sent_messages: list[SentSMS] = []

    async def send_otp(self, phone: str, otp_code: str) -> bool:
        self.sent_messages.append(
            SentSMS(
                phone=phone,
                message=f"[ShopLab] Ma xac thuc OTP cua ban la {otp_code}. Ma co hieu luc trong 5 phut.",
                otp_code=otp_code,
                sent_at=datetime.utcnow(),
            )
        )
        return True

    def get_latest_otp_for_phone(self, phone: str) -> str | None:
        for msg in reversed(self.sent_messages):
            if msg.phone == phone:
                return msg.otp_code
        return None
