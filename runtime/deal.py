"""Deal workspace domain model (BUILD_PLAN D1-M4, vision §4.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DealStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class Deal:
    deal_id: str
    name: str
    target: str
    deal_type: str
    regions: tuple[str, ...]
    expected_window_days: int
    policy_profile_id: str
    created_at: datetime
    status: DealStatus = DealStatus.ACTIVE

    def __post_init__(self) -> None:
        if not self.regions:
            raise ValueError("a deal must declare at least one region (vision §7.8)")
        if self.expected_window_days <= 0:
            raise ValueError("expected_window_days must be positive")
