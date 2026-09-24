"""Pure domain entities for the rule engines (spec §4.1, §5).

Framework-free dataclasses: no SQLAlchemy, no FastAPI, no Celery.
Timezone-aware datetimes only; durations are computed in absolute time.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Employee:
    id: str
    roles: list[str]
    contract_weekly_hours: int
    max_weekly_hours: int
    home_zone: str
    accepts_extra_shifts: bool
    active: bool


@dataclass(frozen=True)
class ShiftSlot:
    """A shift on the schedule (the open one, or any other)."""

    id: str
    location_id: str
    role: str
    starts_at: datetime
    ends_at: datetime
    employee_id: str | None
    status: str = "scheduled"  # scheduled | absent | open | covered


@dataclass(frozen=True)
class AvailabilityBlock:
    employee_id: str
    starts_at: datetime
    ends_at: datetime
    kind: str  # unavailable | preferred_off


@dataclass(frozen=True)
class RescueSettings:
    min_rest_hours: int = 12
    max_coverages_per_14_days: int = 4
    wave_size: int = 3
    wave_interval_minutes: int = 10
    rescue_deadline_minutes_before_start: int = 30


@dataclass(frozen=True)
class Reason:
    """Stable machine code + readable English message (spec §5.1)."""

    code: str
    message: str


@dataclass(frozen=True)
class EligibilityResult:
    employee_id: str
    eligible: bool
    requires_approval: bool
    reasons: tuple[Reason, ...] = field(default_factory=tuple)
