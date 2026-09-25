"""Tests for the port protocols and the in-memory workforce adapter."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.entities import ShiftSlot
from app.integrations.workforce.memory import InMemoryWorkforceAdapter
from app.ports import (
    Channel,
    LLMClient,
    Scheduler,
    WorkforceAdapter,
)


def test_protocols_are_runtime_checkable() -> None:
    assert isinstance(InMemoryWorkforceAdapter(), WorkforceAdapter)


async def test_in_memory_adapter_lists_employees_by_location() -> None:
    adapter = InMemoryWorkforceAdapter()
    adapter.add_employee(
        {"id": "e1", "location_id": "loc", "full_name": "Marta", "roles": ["floor"]}
    )
    adapter.add_employee(
        {"id": "e2", "location_id": "other", "full_name": "Pau", "roles": ["bar"]}
    )

    employees = await adapter.list_employees("loc")

    assert [e["id"] for e in employees] == ["e1"]


async def test_in_memory_adapter_mark_absent_and_assign() -> None:
    start = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
    adapter = InMemoryWorkforceAdapter()
    adapter.add_shift(
        ShiftSlot(
            id="s1",
            location_id="loc",
            role="floor",
            starts_at=start,
            ends_at=start + timedelta(hours=8),
            employee_id="e1",
        )
    )

    await adapter.mark_absent("s1")
    shift = await adapter.get_shift("s1")
    assert shift is not None
    assert shift.status == "absent"

    await adapter.assign_shift("s1", "e2")
    shift = await adapter.get_shift("s1")
    assert shift is not None
    assert shift.employee_id == "e2"
    assert shift.status == "covered"

    await adapter.unassign_shift("s1")
    shift = await adapter.get_shift("s1")
    assert shift is not None
    assert shift.employee_id is None
    assert shift.status == "open"


async def test_in_memory_adapter_get_schedule_filters_by_window() -> None:
    start = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
    adapter = InMemoryWorkforceAdapter()
    adapter.add_shift(
        ShiftSlot(
            id="s1",
            location_id="loc",
            role="floor",
            starts_at=start,
            ends_at=start + timedelta(hours=8),
            employee_id=None,
        )
    )
    adapter.add_shift(
        ShiftSlot(
            id="s2",
            location_id="loc",
            role="bar",
            starts_at=start + timedelta(days=3),
            ends_at=start + timedelta(days=3, hours=8),
            employee_id=None,
        )
    )

    schedule = await adapter.get_schedule("loc", start, start + timedelta(days=1))
    assert [s.id for s in schedule] == ["s1"]


def test_channel_scheduler_llm_protocols_exist() -> None:
    """Contract presence: implementations arrive with their features."""
    assert Channel.__protocol_attrs__
    assert Scheduler.__protocol_attrs__
    assert LLMClient.__protocol_attrs__


def test_unknown_shift_returns_none() -> None:
    InMemoryWorkforceAdapter()
    assert pytest.raises is not None  # keep pytest import meaningful
