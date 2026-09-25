"""Shared worker runtime tests: wiring, handler registration, inbound routing.

All tests are hermetic: SQLite, no provider SDK calls, no network.
"""

import asyncio
import os
import tempfile
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from structlog.testing import capture_logs

import app.runtime as runtime_module
from app.core.clock import SystemClock
from app.core.config import Settings, get_settings
from app.db.models import Base, Employee
from app.runtime import RescueRuntime, build_runtime, reset_worker_runtime
from app.workers.celery_scheduler import CeleryScheduler
from app.workers.scheduler import SimScheduler


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {"_env_file": None, "database_url": "sqlite+aiosqlite://"}
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class FakeOrchestrator:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def task_handlers(self) -> dict[str, Any]:
        return {}

    async def handle_inbound(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def make_runtime(session_factory, orchestrator, interpreter=None) -> RescueRuntime:
    return RescueRuntime(
        session_factory=session_factory,
        channel=runtime_module.TwilioWhatsAppChannel(
            account_sid="", auth_token="", from_number=""
        ),
        workforce=runtime_module.MockWorkforceAdapter(session_factory),
        clock=SystemClock(),
        scheduler=SimScheduler(),
        orchestrator=orchestrator,  # type: ignore[arg-type]
        interpreter=interpreter,
    )


# --- build_runtime: wiring ----------------------------------------------------


def test_build_runtime_degrades_without_a_provider() -> None:
    with capture_logs():
        runtime = build_runtime(make_settings(llm_provider="none"))

    assert runtime.interpreter is None
    assert runtime.orchestrator.interpreter is None


def test_build_runtime_wires_a_configured_interpreter(monkeypatch) -> None:
    stub = object()
    monkeypatch.setattr(runtime_module, "build_interpreter", lambda _settings: stub)

    with capture_logs():
        runtime = build_runtime(make_settings(llm_provider="openai", openai_api_key="k"))

    assert runtime.interpreter is stub
    assert runtime.orchestrator.interpreter is stub


def test_build_runtime_registers_task_handlers_in_the_scheduler() -> None:
    """An unregistered handler would raise KeyError; a registered one runs.

    The scheduler is injected (the same right every test and the eval harness
    has): a temp-file database keeps this hermetic — the test used to reach
    for the ambient DATABASE_URL, which passed on a developer machine with
    Postgres up and failed in CI.
    """
    url = _temp_database_url()
    with capture_logs():
        runtime = build_runtime(
            make_settings(llm_provider="none", database_url=url), scheduler=SimScheduler()
        )

    for name, handler in runtime.orchestrator.task_handlers().items():
        assert runtime.scheduler.handler_for(name) == handler

    runtime.scheduler.schedule(
        datetime.now(UTC) - timedelta(seconds=1), "wave_timeout", {"case_id": "missing"}
    )
    ran = _run(runtime.scheduler)
    assert ran == 1
    assert runtime.scheduler.pending_count() == 0


def _temp_database_url() -> str:
    """Temp-file SQLite database with the schema created (hermetic)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{path}"

    async def create_schema() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(create_schema())
    return url


def _run(scheduler: SimScheduler) -> int:
    return asyncio.run(scheduler.run_due(SystemClock().now()))


def test_get_worker_runtime_is_memoized(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    get_settings.cache_clear()
    reset_worker_runtime()
    try:
        with capture_logs():
            first = runtime_module.get_worker_runtime()
        assert runtime_module.get_worker_runtime() is first
    finally:
        reset_worker_runtime()
        get_settings.cache_clear()


def test_build_runtime_logs_the_llm_path() -> None:
    with capture_logs() as logs:
        build_runtime(make_settings(llm_provider="none"))

    paths = [entry for entry in logs if entry["event"] == "llm_path"]
    assert len(paths) == 1
    assert paths[0]["active"] is False


# --- scheduler backend selection (spec §7.3) ----------------------------------


def test_build_runtime_defaults_to_the_broker_scheduler() -> None:
    """Production timers are owned by the broker, not by worker memory."""
    with capture_logs():
        runtime = build_runtime(make_settings(llm_provider="none"))

    assert isinstance(runtime.scheduler, CeleryScheduler)


def test_build_runtime_picks_the_memory_backend_when_configured() -> None:
    with capture_logs():
        runtime = build_runtime(make_settings(llm_provider="none", scheduler_backend="memory"))

    assert isinstance(runtime.scheduler, SimScheduler)


def test_build_runtime_honours_an_injected_scheduler() -> None:
    injected = SimScheduler()
    with capture_logs():
        runtime = build_runtime(make_settings(llm_provider="none"), scheduler=injected)

    assert runtime.scheduler is injected


def test_build_runtime_rejects_an_unknown_backend() -> None:
    with pytest.raises(ValueError, match="scheduler_backend"), capture_logs():
        build_runtime(make_settings(llm_provider="none", scheduler_backend="redis"))


def test_runtime_circuit_open_is_false_without_interpreter() -> None:
    runtime = make_runtime(None, FakeOrchestrator(), interpreter=None)
    assert runtime.circuit_open() is False


# --- handle_inbound: sender routing (moved from the webhook service) ----------


@pytest.fixture()
async def inbound_world():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            Employee(
                id="emp_1",
                location_id="loc",
                full_name="Marta L.",
                phone_e164="+34600000001",
                language="es",
                roles=["floor"],
                contract_weekly_hours=30,
                max_weekly_hours=40,
                home_zone="port",
                accepts_extra_shifts=True,
                active=True,
            )
        )
        await session.commit()
    yield factory, FakeOrchestrator()
    await engine.dispose()


async def test_runtime_routes_inbound_to_the_orchestrator(inbound_world) -> None:
    factory, orchestrator = inbound_world
    runtime = make_runtime(factory, orchestrator)

    handled = await runtime.handle_inbound("+34600000001", "SM222", "sí")

    assert handled is True
    assert orchestrator.calls[0]["employee_id"] == "emp_1"
    assert orchestrator.calls[0]["provider_message_id"] == "SM222"
    assert orchestrator.calls[0]["conversation_id"] == "conv_twilio_+34600000001"


async def test_runtime_ignores_unknown_senders(inbound_world) -> None:
    factory, orchestrator = inbound_world
    runtime = make_runtime(factory, orchestrator)

    handled = await runtime.handle_inbound("+34999999999", "SM333", "hola")

    assert handled is False
    assert orchestrator.calls == []
