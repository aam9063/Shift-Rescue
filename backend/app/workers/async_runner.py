"""One event loop per worker process.

WHY: the Celery tasks in `app.workers.tasks` run async code from sync task
bodies. The memoized worker runtime (`app.runtime.get_worker_runtime`) holds
a SQLAlchemy async engine whose pooled connections (asyncpg in production)
are bound to the event loop that created them. ``asyncio.run()`` creates a
NEW loop for every call and closes it when the call returns, so the first
tasks after a worker restart succeed (fresh pool) and later tasks reuse a
pooled connection from a dead loop and raise::

    RuntimeError: Task ... got Future ... attached to a different loop

That error cost us real inbound messages on 2026-09-25: the webhook had
already answered 200, so nothing redelivered. `run_async` is the single
place that owns the fix: lazily create ONE loop per process and reuse it
(`run_until_complete`) for every task, so pooled connections always see the
loop they were born on.

Thread-safety: a Celery prefork child executes tasks one at a time, in a
single thread per process, so one loop per process is correct here. This
module is NOT safe for concurrent use from multiple threads.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

# This process's worker loop (created lazily by `_get_process_loop`).
_loop: asyncio.AbstractEventLoop | None = None


def _get_process_loop() -> asyncio.AbstractEventLoop:
    """Return the worker loop, (re)creating it when missing or closed."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        # Libraries that call `asyncio.get_event_loop()` from sync code must
        # see the same loop the tasks run on.
        asyncio.set_event_loop(_loop)
    return _loop


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` on the process's single worker loop and return its result.

    The one-loop-per-process rule lives here — worker tasks must call this
    instead of ``asyncio.run()`` so pooled async database connections stay
    usable across tasks (see the module docstring for why).
    """
    return _get_process_loop().run_until_complete(coro)
