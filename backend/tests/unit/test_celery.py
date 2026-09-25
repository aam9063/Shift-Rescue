"""Unit tests for the Celery app: schedule, inbound task, beat tick (§7.2)."""

from typing import Any

import pytest
from celery.exceptions import Retry
from celery.signals import worker_process_init
from redis.exceptions import RedisError
from structlog.testing import capture_logs

import app.runtime as runtime_module
import app.workers.tasks as tasks
import app.workers.tracing_bootstrap as bootstrap
from app.core.config import Settings, get_settings
from app.workers.celery_app import celery_app
from app.workers.scheduler import SimScheduler


def test_celery_broker_comes_from_settings() -> None:
    assert celery_app.conf.broker_url == get_settings().redis_url
    assert celery_app.conf.result_backend == get_settings().redis_url


def test_ping_task_is_registered() -> None:
    assert "app.workers.celery_app.ping" in celery_app.tasks


def test_retention_purge_task_is_registered() -> None:
    # Celery loads this module through the app's include list (worker startup).
    import app.workers.tasks  # noqa: F401

    assert "app.workers.tasks" in celery_app.conf.include
    assert "app.workers.tasks.purge_old_messages" in celery_app.tasks


# --- beat schedule (spec §7.3) ------------------------------------------------


def test_beat_schedule_ticks_the_scheduler_every_five_seconds() -> None:
    entry = celery_app.conf.beat_schedule["run-due-jobs"]
    assert entry["task"] == "app.workers.tasks.run_due_jobs"
    assert entry["schedule"] == 5.0


def test_beat_schedule_runs_the_retention_purge_daily() -> None:
    entry = celery_app.conf.beat_schedule["purge-old-messages"]
    assert entry["task"] == "app.workers.tasks.purge_old_messages"
    cron = entry["schedule"]
    assert cron.hour == {3}  # 03:00 Europe/Madrid (app timezone)
    assert cron.minute == {0}


# --- task doubles -------------------------------------------------------------


class FakeRuntime:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.scheduler = SimScheduler()
        self.interpreter = None
        self.calls: list[tuple[str, str, str]] = []

    async def handle_inbound(self, from_phone: str, message_sid: str, body: str) -> bool:
        if self._error is not None:
            raise self._error
        self.calls.append((from_phone, message_sid, body))
        return True

    def circuit_open(self) -> bool:
        return False


class FakeRedis:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.writes: list[tuple[str, str, int]] = []

    def set(self, key: str, value: str, ex: int) -> None:
        if self._error is not None:
            raise self._error
        self.writes.append((key, value, ex))


@pytest.fixture()
def fake_runtime(monkeypatch):
    runtime = FakeRuntime()
    monkeypatch.setattr(runtime_module, "get_worker_runtime", lambda: runtime)
    return runtime


# --- process_inbound_message (spec §7.4: idempotent inbound) ------------------


def test_process_inbound_message_calls_the_service(fake_runtime: FakeRuntime) -> None:
    result = tasks.process_inbound_message.apply(args=("+34600000001", "SM1", "hola"))

    assert result.get() is True
    assert fake_runtime.calls == [("+34600000001", "SM1", "hola")]


def test_process_inbound_message_retries_on_a_transient_failure(
    fake_runtime: FakeRuntime, monkeypatch
) -> None:
    """Eager apply cannot re-deliver, so observe the retry signal itself."""
    fake_runtime._error = OSError("connection reset")
    retry_calls: list[dict[str, Any]] = []
    task_instance = tasks.process_inbound_message._orig_run.__self__

    def fake_retry(exc: Exception, **kwargs: Any) -> Retry:
        retry_calls.append({"exc": exc, **kwargs})
        return Retry("retrying")

    monkeypatch.setattr(task_instance, "retry", fake_retry)

    result = tasks.process_inbound_message.apply(args=("+34600000001", "SM1", "hola"))

    assert result.state == "RETRY"
    assert len(retry_calls) == 1
    assert isinstance(retry_calls[0]["exc"], OSError)
    assert retry_calls[0]["countdown"] > 0  # exponential backoff
    assert task_instance.max_retries == 3


def test_process_inbound_message_fails_on_a_permanent_error(
    fake_runtime: FakeRuntime, monkeypatch
) -> None:
    fake_runtime._error = ValueError("bad payload")
    retry_calls: list[dict[str, Any]] = []
    task_instance = tasks.process_inbound_message._orig_run.__self__

    def fake_retry(exc: Exception, **kwargs: Any) -> Retry:
        retry_calls.append({"exc": exc, **kwargs})
        return Retry("retrying")

    monkeypatch.setattr(task_instance, "retry", fake_retry)

    result = tasks.process_inbound_message.apply(args=("+34600000001", "SM1", "hola"))

    assert result.state == "FAILURE"
    assert retry_calls == []


def test_process_inbound_message_logs_the_sid(fake_runtime: FakeRuntime) -> None:
    with capture_logs() as logs:
        tasks.process_inbound_message.apply(args=("+34600000001", "SM1", "hola"))

    events = [entry for entry in logs if entry["event"] == "worker_inbound_processed"]
    assert len(events) == 1
    assert events[0]["message_sid"] == "SM1"
    assert "body" not in str(events[0])


# --- run_due_jobs: tick + snapshot (spec §9.3) --------------------------------


def test_run_due_jobs_publishes_the_snapshot(monkeypatch, fake_runtime: FakeRuntime) -> None:
    client = FakeRedis()
    monkeypatch.setattr(tasks, "_redis_client", lambda: client)

    ran = tasks.run_due_jobs()

    assert ran == 0
    assert len(client.writes) == 1
    key, value, ttl = client.writes[0]
    assert key == tasks.RUNTIME_SNAPSHOT_KEY
    assert ttl == tasks.RUNTIME_SNAPSHOT_TTL_SECONDS
    assert '"llm_configured": false' in value
    assert '"circuit_open": false' in value
    assert '"agent_paused": false' in value


def test_run_due_jobs_swallows_redis_errors(monkeypatch, fake_runtime: FakeRuntime) -> None:
    client = FakeRedis(error=RedisError("connection refused"))
    monkeypatch.setattr(tasks, "_redis_client", lambda: client)

    with capture_logs() as logs:
        ran = tasks.run_due_jobs()

    assert ran == 0
    assert any(e["event"] == "runtime_snapshot_publish_failed" for e in logs)


# --- worker tracing bootstrap (spec §9.1: spans from the worker) --------------


def test_worker_process_init_configures_tracing_with_current_settings(monkeypatch) -> None:
    calls: list[Settings] = []

    def fake_configure(settings: Settings) -> bool:
        calls.append(settings)
        return True

    monkeypatch.setattr(bootstrap, "configure_tracing", fake_configure)

    results = worker_process_init.send(sender=None)

    assert any(r.__name__ == "_init_worker_tracing" for r, _ in results)
    assert calls == [get_settings()]


def test_worker_process_init_is_a_noop_when_tracing_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap, "configure_tracing", lambda _settings: False)

    with capture_logs() as logs:
        worker_process_init.send(sender=None)  # no raise

    assert any(
        e["event"] == "worker_tracing_bootstrap" and e["installed"] is False for e in logs
    )


def test_worker_process_init_swallows_configure_failures(monkeypatch) -> None:
    def boom(_settings: Settings) -> bool:
        raise RuntimeError("otel exploded")

    monkeypatch.setattr(bootstrap, "configure_tracing", boom)

    with capture_logs() as logs:
        worker_process_init.send(sender=None)  # never raise

    failures = [e for e in logs if e["event"] == "worker_tracing_bootstrap_failed"]
    assert len(failures) == 1
    assert "otel exploded" in failures[0]["error"]
