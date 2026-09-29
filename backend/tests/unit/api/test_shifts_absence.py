"""POST /api/shifts/{id}/absence (spec §7.5): the manager marks an absence.

The manager action is authoritative: 202 after the Celery enqueue, 404 when
the shift is unknown or outside the manager's locations, 409 when the shift
is already absent or already has a live rescue — the detail says which. No
demo gate: production behaviour. No broker: the enqueue is stubbed (the API
suite autouse fixture plus the explicit recorder below).
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import RescueCase, Shift
from app.workers.tasks import mark_shift_absence_task
from tests.conftest import ABSENT_ID, LOCATION_ID, NOW, SHIFT_ID, auth_headers

SCHEDULED_SHIFT_ID = "shift_scheduled"


class StubTask:
    """Records `.delay` calls (replaces the suite-wide no-op recorder)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def delay(self, *args) -> None:
        self.calls.append(args)


@pytest.fixture()
def stub_absence(monkeypatch):
    stub = StubTask()
    monkeypatch.setattr(mark_shift_absence_task, "delay", stub.delay)
    return stub


async def _add_scheduled_shift(
    sessions,
    *,
    shift_id: str = SCHEDULED_SHIFT_ID,
    location_id: str = LOCATION_ID,
) -> str:
    async with sessions() as session:
        session.add(
            Shift(
                id=shift_id,
                location_id=location_id,
                role="bar",
                starts_at=NOW + timedelta(hours=4),
                ends_at=NOW + timedelta(hours=12),
                employee_id=ABSENT_ID,
                status="scheduled",
            )
        )
        await session.commit()
    return shift_id


async def _add_live_case(sessions, shift_id: str) -> None:
    async with sessions() as session:
        session.add(
            RescueCase(
                id="res_live",
                location_id=LOCATION_ID,
                shift_id=shift_id,
                absent_employee_id=ABSENT_ID,
                origin="employee_message",
                status="OFFERING",
                opened_at=NOW,
                deadline_at=NOW + timedelta(minutes=30),
            )
        )
        await session.commit()


async def test_marks_absence_returns_202_and_enqueues(client, world, stub_absence) -> None:
    shift_id = await _add_scheduled_shift(world.sessions)
    response = await client.post(f"/api/shifts/{shift_id}/absence", headers=auth_headers())
    assert response.status_code == 202
    assert response.json() == {"status": "queued", "id": shift_id}
    assert stub_absence.calls == [(shift_id, "mgr_1", None)]


async def test_optional_reason_is_passed_through_to_the_task(client, world, stub_absence) -> None:
    shift_id = await _add_scheduled_shift(world.sessions)
    response = await client.post(
        f"/api/shifts/{shift_id}/absence",
        json={"reason": "llamo y no contesta"},
        headers=auth_headers(),
    )
    assert response.status_code == 202
    assert stub_absence.calls == [(shift_id, "mgr_1", "llamo y no contesta")]


async def test_unknown_shift_404(client, world, stub_absence) -> None:
    response = await client.post("/api/shifts/shift_missing/absence", headers=auth_headers())
    assert response.status_code == 404
    assert stub_absence.calls == []


async def test_shift_outside_the_manager_locations_404(client, world, stub_absence) -> None:
    shift_id = await _add_scheduled_shift(
        world.sessions, shift_id="shift_other", location_id="loc_other"
    )
    response = await client.post(f"/api/shifts/{shift_id}/absence", headers=auth_headers())
    assert response.status_code == 404
    assert stub_absence.calls == []


async def test_already_absent_409_names_the_conflict(client, world, stub_absence) -> None:
    # The seeded world's shift is already marked absent (spec §7.5).
    response = await client.post(f"/api/shifts/{SHIFT_ID}/absence", headers=auth_headers())
    assert response.status_code == 409
    assert "already marked absent" in response.json()["detail"]
    assert stub_absence.calls == []


async def test_live_rescue_409_names_the_conflict(client, world, stub_absence) -> None:
    shift_id = await _add_scheduled_shift(world.sessions)
    await _add_live_case(world.sessions, shift_id)
    response = await client.post(f"/api/shifts/{shift_id}/absence", headers=auth_headers())
    assert response.status_code == 409
    assert "already running" in response.json()["detail"]
    assert stub_absence.calls == []


async def test_requires_manager_jwt(client, world, stub_absence) -> None:
    response = await client.post(f"/api/shifts/{SCHEDULED_SHIFT_ID}/absence")
    assert response.status_code == 401
    assert stub_absence.calls == []


async def test_enqueue_failure_is_a_loud_500(client, world, stub_absence, monkeypatch) -> None:
    shift_id = await _add_scheduled_shift(world.sessions)

    def boom(*args) -> None:
        raise RuntimeError("broker down")

    monkeypatch.setattr(mark_shift_absence_task, "delay", boom)
    response = await client.post(f"/api/shifts/{shift_id}/absence", headers=auth_headers())
    assert response.status_code == 500


async def test_absence_leaves_world_data_untouched(client, world, stub_absence) -> None:
    """The API never applies the domain change inline: the worker owns it."""
    shift_id = await _add_scheduled_shift(world.sessions)
    await client.post(f"/api/shifts/{shift_id}/absence", headers=auth_headers())
    async with world.sessions() as session:
        shift = (
            await session.execute(select(Shift).where(Shift.id == shift_id))
        ).scalar_one()
    assert shift.status == "scheduled"  # still untouched until the worker runs
