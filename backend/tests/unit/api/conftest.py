"""Unit-level API suite: hermetic by default.

A unit test must never need a broker. The routes under test enqueue Celery
tasks, and `Task.delay` talks to Redis: on a development machine that broker is
usually up, so a test that forgets to stub it passes locally and fails in CI with
a retry storm ("Retry limit exceeded while trying to reconnect to the Celery
result store"). This autouse fixture removes that ambient dependency for the
whole suite; tests that assert the enqueue still install their own recorder,
which simply replaces this one.
"""

import pytest

from app.workers.tasks import (
    apply_scheduled_job,
    close_rescue_task,
    mark_shift_absence_task,
    process_inbound_message,
    reconcile_stale_cases,
)

_ENQUEUING_TASKS = (
    process_inbound_message,
    reconcile_stale_cases,
    apply_scheduled_job,
    close_rescue_task,
    mark_shift_absence_task,
)

_calls: list[tuple[str, tuple]] = []


def _record(name: str):
    def delay(*args, **kwargs) -> None:
        _calls.append((name, args))

    return delay


@pytest.fixture(autouse=True)
def no_broker(monkeypatch):
    """Every enqueue is swallowed unless the test stubs it explicitly."""
    _calls.clear()
    for task in _ENQUEUING_TASKS:
        monkeypatch.setattr(task, "delay", _record(task.name))
    return _calls
