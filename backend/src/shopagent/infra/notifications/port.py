"""Notification port and in-memory / SMTP adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
import uuid


@dataclass
class NotificationMessage:
    customer_id: uuid.UUID
    channel: str  # email, sms, in_app
    template: str
    payload: dict[str, Any]


class NotificationPort(ABC):
    @abstractmethod
    async def send(self, notification: NotificationMessage) -> bool:
        pass


class InAppNotificationAdapter(NotificationPort):
    def __init__(self) -> None:
        self.sent_notifications: list[NotificationMessage] = []

    async def send(self, notification: NotificationMessage) -> bool:
        self.sent_notifications.append(notification)
        return True
