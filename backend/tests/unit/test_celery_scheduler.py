"""Unit tests for the broker-owned scheduler (spec §7.3).

`CeleryScheduler` publishes one deferred Celery task per timer; the fake task
below stands in for the broker so these tests never need Redis.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core.clock import FakeClock
from app.workers.celery_scheduler import CeleryScheduler
from app.workers.scheduler import SimScheduler


class FakeResult:
    def __init__(self, id: str) -> None:
        self.id = id


class FakeCeleryTask:
    """Stands in for `apply_scheduled_job`; records what would hit the broker."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def apply_async(self, *, kwargs: dict[str, Any], countdown: float) -> FakeResult:
        self.calls.append({"kwargs": kwargs, "countdown": countdown})
        return FakeResult(f"broker_{len(self.calls)}")


def make_scheduler(
    clock: FakeClock | None = None,
) -> tuple[CeleryScheduler, FakeCeleryTask, FakeClock]:
    clock = clock or FakeClock(datetime(2026, 10, 3, 14, 0, tzinfo=UTC))
    task = FakeCeleryTask()
    return CeleryScheduler(clock, task=task), task, clock


def test_schedule_computes_the_countdown_from_the_clock() -> None:
    scheduler, task, clock = make_scheduler()

    job_id = scheduler.schedule(
        datetime(2026, 10, 3, 14, 2, 30, tzinfo=UTC), "rescue_deadline", {"case_id": "case_1"}
    )

    assert task.calls == [
        {
            "kwargs": {"task_name": "rescue_deadline", "payload": {"case_id": "case_1"}},
            "countdown": 150.0,
        }
    ]
    assert job_id == "broker_1"  # derived from the broker task id


def test_schedule_clamps_an_already_past_run_at_to_zero() -> None:
    """The reconcile sweep re-enqueues overdue timers: they must run now."""
    scheduler, task, _ = make_scheduler()

    scheduler.schedule(
        datetime(2026, 10, 3, 13, 0, tzinfo=UTC), "rescue_deadline", {"case_id": "case_1"}
    )

    assert task.calls[0]["countdown"] == 0.0


def test_schedule_respects_the_clock_between_calls() -> None:
    clock = FakeClock(datetime(2026, 10, 3, 14, 0, tzinfo=UTC))
    scheduler, task, _ = make_scheduler(clock)

    run_at = clock.now() + timedelta(minutes=5)
    scheduler.schedule(run_at, "wave_timeout", {"case_id": "c1"})
    clock.advance(timedelta(minutes=3))
    # The same absolute run_at, scheduled from a later clock: less time left.
    scheduler.schedule(run_at, "wave_timeout", {"case_id": "c2"})

    assert [c["countdown"] for c in task.calls] == [300.0, 120.0]


def test_handler_for_resolves_the_registered_handler() -> None:
    scheduler, _, _ = make_scheduler()

    async def handler(payload: dict[str, Any]) -> None:  # pragma: no cover
        return None

    scheduler.register("rescue_deadline", handler)
    assert scheduler.handler_for("rescue_deadline") is handler


async def test_handler_for_raises_on_an_unknown_name() -> None:
    """A timer whose handler is missing must be loud, never silent."""
    scheduler, _, _ = make_scheduler()
    with pytest.raises(KeyError, match="no_such_task"):
        scheduler.handler_for("no_such_task")


def test_pending_count_is_zero_the_broker_owns_the_queue() -> None:
    scheduler, task, _ = make_scheduler()
    scheduler.schedule(datetime(2026, 10, 3, 14, 30, tzinfo=UTC), "wave_timeout", {"case_id": "c"})
    assert task.calls  # a timer was published
    assert scheduler.pending_count() == 0


async def test_run_due_is_a_no_op_the_broker_owns_due_ness() -> None:
    scheduler, _, _ = make_scheduler()
    ran = await scheduler.run_due(datetime(2026, 10, 3, 15, 0, tzinfo=UTC))
    assert ran == 0


def test_sim_scheduler_exposes_handler_for() -> None:
    """The port accessor exists on both backends; nothing reaches `_handlers`."""

    async def handler(payload: dict[str, Any]) -> None:  # pragma: no cover
        return None

    scheduler = SimScheduler()
    scheduler.register("rescue_deadline", handler)
    assert scheduler.handler_for("rescue_deadline") is handler
    with pytest.raises(KeyError, match="unknown_task"):
        scheduler.handler_for("unknown_task")
