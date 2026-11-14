"""Carrier tracking port and simulated carrier adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ShipmentTrackingEvent:
    status: str
    location: str
    occurred_at: datetime
    description: str


@dataclass
class ShipmentTrackingInfo:
    tracking_code: str
    carrier: str
    current_status: str
    events: list[ShipmentTrackingEvent]


class CarrierPort(ABC):
    @abstractmethod
    async def track(self, tracking_code: str) -> ShipmentTrackingInfo | None:
        pass


class SimulatedCarrier(CarrierPort):
    def __init__(self) -> None:
        self._shipments: dict[str, ShipmentTrackingInfo] = {}

    async def track(self, tracking_code: str) -> ShipmentTrackingInfo | None:
        return self._shipments.get(tracking_code)

    def set_tracking_info(self, info: ShipmentTrackingInfo) -> None:
        self._shipments[info.tracking_code] = info
