"""Port protocols (spec §7.3).

All external effects behind `Protocol` interfaces: the domain and services
depend on these, never on concrete SDKs (Twilio, Strands, Celery, SQLAlchemy).
"""

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.domain.entities import ShiftSlot


@runtime_checkable
class Scheduler(Protocol):
    """Schedules delayed work (Celery in prod, in-memory queue in sims)."""

    def schedule(self, run_at: datetime, task_name: str, payload: dict[str, Any]) -> str:
        """Enqueue `task_name` to run at `run_at`; returns the scheduled task id."""
        ...


@runtime_checkable
class Channel(Protocol):
    """Outbound message channel (Twilio WhatsApp in prod, simulated in demo)."""

    async def send(
        self,
        recipient_phone_e164: str,
        body: str,
        *,
        template_key: str | None = None,
        rescue_id: str | None = None,
    ) -> str:
        """Send a message; returns the provider message id."""
        ...


@runtime_checkable
class WorkforceAdapter(Protocol):
    """Read/write access to the client's HR system (mock implementation for MVP)."""

    async def list_employees(self, location_id: str) -> list[dict[str, Any]]: ...

    async def get_schedule(
        self, location_id: str, from_dt: datetime, to_dt: datetime
    ) -> list[ShiftSlot]: ...

    async def get_shift(self, shift_id: str) -> ShiftSlot | None: ...

    async def mark_absent(self, shift_id: str) -> None: ...

    async def assign_shift(self, shift_id: str, employee_id: str) -> None: ...

    async def unassign_shift(self, shift_id: str) -> None: ...


@runtime_checkable
class LLMClient(Protocol):
    """Thin LLM wrapper (Strands in prod, replay in tests). No tools that mutate state."""

    async def interpret(self, message_body: str, context: dict[str, Any]) -> dict[str, Any]:
        """Structured interpretation of an inbound message (spec §6.2)."""
        ...
