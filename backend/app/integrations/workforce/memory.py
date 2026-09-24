"""In-memory WorkforceAdapter implementation (tests, demos, eval harness)."""

from datetime import datetime

from app.domain.entities import ShiftSlot


class InMemoryWorkforceAdapter:
    """Deterministic fake of the HR system backed by dicts."""

    def __init__(self) -> None:
        self._employees: list[dict] = []
        self._shifts: dict[str, ShiftSlot] = {}

    def add_employee(self, employee: dict) -> None:
        self._employees.append(dict(employee))

    def add_shift(self, shift: ShiftSlot) -> None:
        self._shifts[shift.id] = shift

    async def list_employees(self, location_id: str) -> list[dict]:
        return [e for e in self._employees if e.get("location_id") == location_id]

    async def get_schedule(
        self, location_id: str, from_dt: datetime, to_dt: datetime
    ) -> list[ShiftSlot]:
        return [
            s
            for s in self._shifts.values()
            if s.location_id == location_id and from_dt <= s.starts_at < to_dt
        ]

    async def get_shift(self, shift_id: str) -> ShiftSlot | None:
        return self._shifts.get(shift_id)

    async def mark_absent(self, shift_id: str) -> None:
        shift = self._shifts.get(shift_id)
        if shift is None:
            raise KeyError(f"Unknown shift: {shift_id}")
        self._shifts[shift_id] = _replace(shift, status="absent")

    async def assign_shift(self, shift_id: str, employee_id: str) -> None:
        shift = self._shifts.get(shift_id)
        if shift is None:
            raise KeyError(f"Unknown shift: {shift_id}")
        self._shifts[shift_id] = _replace(shift, employee_id=employee_id, status="covered")

    async def unassign_shift(self, shift_id: str) -> None:
        shift = self._shifts.get(shift_id)
        if shift is None:
            raise KeyError(f"Unknown shift: {shift_id}")
        self._shifts[shift_id] = _replace(shift, employee_id=None, status="open")


def _replace(shift: ShiftSlot, **changes: object) -> ShiftSlot:
    from dataclasses import replace

    return replace(shift, **changes)  # type: ignore[arg-type]
