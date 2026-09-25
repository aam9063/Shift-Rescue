"""CeleryScheduler (spec §7.3): timers owned by the broker.

Root cause this class fixes: the in-memory `SimScheduler` is a per-process
object, and the worker runs Celery's default prefork pool (12 children, each
with its own singleton runtime and therefore its own scheduler). The task
that opened a case registered the deadline timer in *its own* child's queue,
while the beat tick (`run_due_jobs`) landed in whichever child Celery picked —
with its own, empty scheduler. They practically never coincided, so
`run_due` always found zero due jobs and no timer ever fired.

Here the broker owns the queue: `schedule()` publishes one deferred Celery
task (`apply_scheduled_job`) whose countdown is computed from the injected
clock. Any free worker child executes it at the right time, and a pending
timer survives a worker restart because it lives in Redis, not in process
memory. Handlers are resolved in the *executing* process: every worker
registers the same handlers at runtime build time, so the deferred task looks
its handler up locally (`handler_for`).
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from app.core.clock import Clock

Handler = Callable[[dict[str, Any]], Awaitable[None]]


def _deferred_task() -> Any:
    """The Celery task that executes one scheduled timer in a worker child.

    Imported lazily: `app.workers.tasks` builds the runtime lazily too, and an
    eager import here would create an import cycle with `app.runtime`.
    """
    from app.workers.tasks import apply_scheduled_job

    return apply_scheduled_job


class CeleryScheduler:
    """`Scheduler` port backed by deferred Celery tasks (one per timer)."""

    def __init__(self, clock: Clock, *, task: Any = None) -> None:
        self._clock = clock
        # Injectable so tests never need a broker; production resolves the
        # deferred task lazily on the first `schedule()` call.
        self._task = task
        self._handlers: dict[str, Handler] = {}

    def register(self, task_name: str, handler: Handler) -> None:
        """Register the handler this process will execute for `task_name`."""
        self._handlers[task_name] = handler

    def handler_for(self, task_name: str) -> Handler:
        """Resolve the handler for `task_name` in the executing process.

        An unknown name is a hard failure: a timer whose handler is missing
        must be loud, never silently dropped.
        """
        try:
            return self._handlers[task_name]
        except KeyError:
            raise KeyError(f"No handler registered for task '{task_name}'") from None

    def schedule(self, run_at: datetime, task_name: str, payload: dict[str, Any]) -> str:
        """Publish one deferred broker task; returns the broker task id.

        The countdown is clamped at zero so an already-past `run_at` (a timer
        restored after downtime, or the reconcile sweep) executes immediately
        instead of being rejected by the broker.
        """
        task = self._task if self._task is not None else _deferred_task()
        countdown = max(0.0, (run_at - self._clock.now()).total_seconds())
        result = task.apply_async(
            kwargs={"task_name": task_name, "payload": payload},
            countdown=countdown,
        )
        return str(result.id)

    def pending_count(self) -> int:
        """Always 0: the broker owns the queue now.

        The in-memory queue is gone, so this process cannot count pending
        timers without querying the broker; nothing in production reads this
        number (it exists only for `Scheduler` port compatibility with
        `SimScheduler`). Timer visibility lives in Redis/broker tooling.
        """
        return 0

    async def run_due(self, now: datetime) -> int:
        """Always 0 and never executes anything: the broker owns due-ness.

        There is no local queue to scan — the broker delivers each timer when
        its countdown expires. The beat tick (`run_due_jobs`) remains only for
        the `memory` backend and the status-snapshot refresh; calling this on
        a `CeleryScheduler` is a harmless no-op.
        """
        return 0
