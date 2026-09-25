"""Unit tests for the worker's one-loop-per-process runner (`run_async`).

Regression for the 2026-09-25 production incident: `tasks.py` used
`asyncio.run()` per task, so async database connections pooled by the memoized
worker runtime stayed bound to the loop `asyncio.run()` closes when it
returns. The first tasks after a worker restart succeeded (fresh pool); later
tasks reused a pooled connection from a dead loop and raised
``RuntimeError: Task ... got Future ... attached to a different loop`` — and
the inbound message was lost, because the webhook had already answered 200.

`run_async` (app.workers.async_runner) keeps ONE loop per worker process.

Note on the database double: aiosqlite creates a fresh future per `_execute`
call (verified in aiosqlite 0.22.1), so plain `sqlite+aiosqlite` cannot
reproduce the cross-loop failure. `LoopBoundConnection` below reproduces
asyncpg's binding mechanics — one result future per connection, completed on
the loop that owns it — over a real SQLite file database.
"""

import asyncio
import sqlite3
from typing import Any

import pytest

import app.workers.async_runner as runner


@pytest.fixture(autouse=True)
def fresh_process_loop():
    """Isolate the module-level loop state between tests."""
    saved = runner._loop
    runner._loop = None
    yield
    created = runner._loop
    runner._loop = saved
    if created is not None and created is not saved and not created.is_closed():
        created.close()


def test_run_async_returns_the_coroutine_result() -> None:
    async def value() -> int:
        return 42

    assert runner.run_async(value()) == 42


def test_run_async_reuses_the_same_loop_across_calls() -> None:
    seen: list[asyncio.AbstractEventLoop] = []

    async def probe() -> str:
        seen.append(asyncio.get_running_loop())
        return "ok"

    assert runner.run_async(probe()) == "ok"
    assert runner.run_async(probe()) == "ok"

    assert len(seen) == 2
    assert seen[0] is seen[1]  # one loop object, not a fresh one per call
    assert seen[0] is runner._get_process_loop()


def test_run_async_sets_the_process_loop_as_current() -> None:
    async def noop() -> None:
        return None

    runner.run_async(noop())

    assert asyncio.get_event_loop() is runner._get_process_loop()


def test_run_async_recovers_from_a_closed_loop() -> None:
    first = runner._get_process_loop()
    first.close()

    async def value() -> str:
        return "recovered"

    assert runner.run_async(value()) == "recovered"
    assert runner._get_process_loop() is not first


class LoopBoundConnection:
    """Async SQLite connection with asyncpg-style loop binding.

    The result future is created once, at connect time, and completed on the
    loop that owns the connection — how a real network protocol (asyncpg)
    works. A task on a different loop awaiting that future raises exactly the
    production failure: "got Future attached to a different loop".
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._loop: asyncio.AbstractEventLoop | None = None
        self._conn: sqlite3.Connection | None = None
        self._result: asyncio.Future[Any] | None = None

    async def connect(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._conn = sqlite3.connect(self._path)
        self._conn.execute("create table seen (sid text not null)")
        self._conn.commit()
        self._result = self._loop.create_future()

    async def insert_and_count(self, sid: str) -> int:
        assert self._loop is not None
        assert self._conn is not None
        assert self._result is not None
        self._conn.execute("insert into seen (sid) values (?)", (sid,))
        self._conn.commit()
        rows = self._conn.execute("select count(*) from seen").fetchall()
        future = self._result
        if not self._loop.is_closed():
            # A protocol completes its futures from the loop that owns them;
            # from a worker thread that is call_soon_threadsafe.
            self._loop.call_soon_threadsafe(future.set_result, rows)
        result = await future  # raises on a different loop, like asyncpg
        self._result = self._loop.create_future()
        return int(result[0][0])


class PooledRuntime:
    """Stands in for the memoized worker runtime: one pooled connection
    created by the first task and reused by every later task in the process —
    what `get_worker_runtime()` does with its SQLAlchemy async engine."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._connection: LoopBoundConnection | None = None

    async def record_inbound(self, sid: str) -> int:
        if self._connection is None:
            self._connection = LoopBoundConnection(self._path)
            await self._connection.connect()
        return await self._connection.insert_and_count(sid)


def test_two_consecutive_calls_reuse_a_pooled_connection(tmp_path) -> None:
    """THE regression test for the production incident.

    Two consecutive worker calls run coroutines that use a pooled async
    database connection over a temp-file SQLite database. With the old
    per-task `asyncio.run()` behaviour the second call reuses a connection
    bound to the first call's (now closed) loop and raises
    "got Future attached to a different loop" — losing the message.
    """
    db_path = tmp_path / "shift.db"
    runtime = PooledRuntime(str(db_path))

    async def task(sid: str) -> int:
        return await runtime.record_inbound(sid)

    assert runner.run_async(task("SM1")) == 1
    assert runner.run_async(task("SM2")) == 2
