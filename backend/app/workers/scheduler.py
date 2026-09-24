"""SimScheduler (spec §7.3): in-memory queue driven by a FakeClock.

Executes a full rescue timeline of simulated hours in milliseconds. Each
task name maps to a registered async handler; production wires the same
handlers to Celery tasks.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

Handler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(order=True)
class _Job:
    run_at: datetime
    seq: int
    job_id: str = field(compare=False)
    task_name: str = field(compare=False)
    payload: dict[str, Any] = field(compare=False)


class SimScheduler:
    def __init__(self, handlers: dict[str, Handler] | None = None) -> None:
        self._handlers: dict[str, Handler] = dict(handlers or {})
        self._jobs: list[_Job] = []
        self._seq = 0

    def register(self, task_name: str, handler: Handler) -> None:
        self._handlers[task_name] = handler

    def schedule(self, run_at: datetime, task_name: str, payload: dict[str, Any]) -> str:
        self._seq += 1
        job_id = f"job_{self._seq}"
        self._jobs.append(
            _Job(
                run_at=run_at,
                seq=self._seq,
                job_id=job_id,
                task_name=task_name,
                payload=payload,
            )
        )
        return job_id

    def pending_count(self) -> int:
        return len(self._jobs)

    async def run_due(self, now: datetime) -> int:
        """Execute every job whose run_at <= now, in scheduled order."""
        due = sorted((j for j in self._jobs if j.run_at <= now), key=lambda j: (j.run_at, j.seq))
        executed = 0
        for job in due:
            self._jobs.remove(job)
            handler = self._handlers.get(job.task_name)
            if handler is None:
                raise KeyError(f"No handler registered for task '{job.task_name}'")
            await handler(job.payload)
            executed += 1
        return executed
