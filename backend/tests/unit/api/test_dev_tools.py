"""Dev-tools endpoint tests (spec §7.5, decisions 1-3).

The simulator must inject into the real pipeline (the same task the Twilio
webhook enqueues, stubbed here), be double-gated (router not advertised and
hard 404 outside demo environments) and require a manager JWT. The clock
moves a Redis offset (faked) and re-enqueues the reconcile sweep. All tests
are hermetic: no Redis, no broker, no database beyond the seeded SQLite world.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from structlog.testing import capture_logs

from app.api.dev_tools import get_demo_redis
from app.core.clock import DEMO_CLOCK_OFFSET_KEY
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import create_app
from app.workers.tasks import process_inbound_message, reconcile_stale_cases
from tests.conftest import TEST_SETTINGS, auth_headers

EMPLOYEE_ID = "emp_1"
EMPLOYEE_PHONE = "+34600000001"


class StubTask:
    """Records `.delay` calls; raises when armed (enqueue failure path)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.error: Exception | None = None

    def delay(self, *args) -> None:
        if self.error is not None:
            raise self.error
        self.calls.append(args)


class FakeRedis:
    """Minimal Redis stand-in: `get`/`set`/`incrby` over the offset key only."""

    def __init__(self, initial: int | None = None) -> None:
        self.values: dict[str, str] = (
            {} if initial is None else {DEMO_CLOCK_OFFSET_KEY: str(initial)}
        )

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def incrby(self, key: str, amount: int) -> str:
        self.values[key] = str(int(self.values.get(key, "0")) + amount)
        return self.values[key]


@pytest.fixture()
def stub_inbound(monkeypatch):
    stub = StubTask()
    monkeypatch.setattr(process_inbound_message, "delay", stub.delay)
    return stub


@pytest.fixture()
def stub_sweep(monkeypatch):
    stub = StubTask()
    monkeypatch.setattr(reconcile_stale_cases, "delay", stub.delay)
    return stub


def make_client(
    world, redis: FakeRedis, app_env: str, monkeypatch
) -> tuple[httpx.AsyncClient, FastAPI]:
    """Build the app deterministically: the router is registered exactly when
    `APP_ENV` is a demo one, and settings/DB/Redis come from overrides."""
    monkeypatch.setenv("APP_ENV", app_env)
    get_settings.cache_clear()
    application = create_app()

    async def override_session():
        async with world.sessions() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[get_settings] = lambda: TEST_SETTINGS
    application.dependency_overrides[get_demo_redis] = lambda: redis
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    )
    return client, application


@pytest.fixture()
async def dev_client(world, fake_redis: FakeRedis, monkeypatch):
    client, application = make_client(world, fake_redis, "local", monkeypatch)
    async with client:
        yield client
    application.dependency_overrides.clear()
    monkeypatch.delenv("APP_ENV", raising=False)
    get_settings.cache_clear()


@pytest.fixture()
def fake_redis():
    return FakeRedis()


# --- simulator: same pipeline as the Twilio webhook ----------------------------


async def test_simulated_message_enqueues_the_inbound_task(dev_client, stub_inbound) -> None:
    response = await dev_client.post(
        f"/dev/simulator/{EMPLOYEE_ID}/messages",
        json={"text": "no puedo venir hoy"},
        headers=auth_headers(),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["id"].startswith("sim_")
    assert stub_inbound.calls == [(EMPLOYEE_PHONE, body["id"], "no puedo venir hoy")]


async def test_simulated_message_unknown_employee_404(dev_client, stub_inbound) -> None:
    response = await dev_client.post(
        "/dev/simulator/emp_missing/messages",
        json={"text": "hola"},
        headers=auth_headers(),
    )

    assert response.status_code == 404
    assert stub_inbound.calls == []


async def test_simulated_message_requires_a_token(dev_client) -> None:
    response = await dev_client.post(
        f"/dev/simulator/{EMPLOYEE_ID}/messages",
        json={"text": "hola"},
    )

    assert response.status_code == 401


async def test_simulated_message_enqueue_failure_is_loud(
    dev_client, stub_inbound, monkeypatch
) -> None:
    stub_inbound.error = ConnectionError("broker down")

    response = await dev_client.post(
        f"/dev/simulator/{EMPLOYEE_ID}/messages",
        json={"text": "hola"},
        headers=auth_headers(),
    )

    assert response.status_code == 500


# --- demo clock: shared offset plus the reconcile sweep ------------------------


async def test_clock_advance_moves_the_offset_and_enqueues_the_sweep(
    dev_client, fake_redis, stub_sweep
) -> None:
    before = datetime.now(UTC)

    response = await dev_client.post(
        "/dev/clock/advance", json={"seconds": 600}, headers=auth_headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["offsetSeconds"] == 600
    virtual = datetime.fromisoformat(body["now"])
    assert before + timedelta(seconds=595) <= virtual <= datetime.now(UTC) + timedelta(
        seconds=605
    )
    assert fake_redis.values[DEMO_CLOCK_OFFSET_KEY] == "600"
    assert stub_sweep.calls == [()]


async def test_clock_advance_accepts_negative_seconds(dev_client, fake_redis) -> None:
    response = await dev_client.post(
        "/dev/clock/advance", json={"seconds": -120}, headers=auth_headers()
    )

    assert response.status_code == 200
    assert response.json()["offsetSeconds"] == -120
    assert fake_redis.values[DEMO_CLOCK_OFFSET_KEY] == "-120"


async def test_clock_advance_rejects_an_unsane_bound(dev_client) -> None:
    response = await dev_client.post(
        "/dev/clock/advance",
        json={"seconds": 60 * 24 * 3600},  # 60 days > the 30-day bound
        headers=auth_headers(),
    )

    assert response.status_code == 422


async def test_clock_reset_zeroes_the_offset_and_enqueues_the_sweep(
    dev_client, fake_redis, stub_sweep
) -> None:
    # A leftover offset from testing (+18 h 50 m) is exactly the case reset
    # exists for: the whole worker saw "now" a day ahead.
    fake_redis.values[DEMO_CLOCK_OFFSET_KEY] = "67800"
    before = datetime.now(UTC)

    response = await dev_client.post("/dev/clock/reset", headers=auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["offsetSeconds"] == 0
    assert fake_redis.values[DEMO_CLOCK_OFFSET_KEY] == "0"
    assert stub_sweep.calls == [()]
    virtual = datetime.fromisoformat(body["now"])
    assert abs(virtual - before) < timedelta(seconds=5)


async def test_clock_reset_requires_a_token(dev_client) -> None:
    response = await dev_client.post("/dev/clock/reset")

    assert response.status_code == 401


async def test_get_clock_reports_virtual_time_and_offset(dev_client, fake_redis) -> None:
    empty = await dev_client.get("/dev/clock", headers=auth_headers())
    assert empty.status_code == 200
    assert empty.json()["offsetSeconds"] == 0

    fake_redis.values[DEMO_CLOCK_OFFSET_KEY] = "3600"
    advanced = await dev_client.get("/dev/clock", headers=auth_headers())
    assert advanced.json()["offsetSeconds"] == 3600
    virtual = datetime.fromisoformat(advanced.json()["now"])
    assert abs(virtual - (datetime.now(UTC) + timedelta(hours=1))) < timedelta(seconds=5)


async def test_get_clock_degrades_when_redis_fails(world, monkeypatch) -> None:
    class BrokenRedis:
        def get(self, key: str) -> str:
            raise ConnectionError("redis down")

    client, application = make_client(world, BrokenRedis(), "local", monkeypatch)
    async with client as async_client:
        with capture_logs() as logs:
            response = await async_client.get("/dev/clock", headers=auth_headers())

    assert response.status_code == 200
    assert response.json()["offsetSeconds"] == 0
    assert any(e["event"] == "demo_clock_offset_read_failed" for e in logs)
    application.dependency_overrides.clear()
    get_settings.cache_clear()


# --- the demo gate: not advertised and a hard 404 outside demo environments ----


async def test_dev_routes_are_not_advertised_or_served_in_production(world, monkeypatch) -> None:
    client, application = make_client(world, FakeRedis(), "production", monkeypatch)
    async with client as async_client:
        paths = application.openapi()["paths"]
        clock_response = await async_client.get("/dev/clock", headers=auth_headers())
        reset_response = await async_client.post("/dev/clock/reset", headers=auth_headers())

    assert not [path for path in paths if "/dev/" in path]
    assert clock_response.status_code == 404
    assert reset_response.status_code == 404
    application.dependency_overrides.clear()
    get_settings.cache_clear()


async def test_dev_routes_answer_404_when_settings_change_after_startup(
    world, fake_redis, monkeypatch
) -> None:
    """The second gate: even with the router registered, a non-demo settings
    object at request time answers 404 (never 401/403 — it does not exist)."""
    client, application = make_client(world, fake_redis, "local", monkeypatch)
    production = Settings(
        jwt_secret=TEST_SETTINGS.jwt_secret, app_env="production", _env_file=None
    )
    application.dependency_overrides[get_settings] = lambda: production
    async with client as async_client:
        response = await async_client.post(
            "/dev/clock/advance", json={"seconds": 60}, headers=auth_headers()
        )

    assert response.status_code == 404
    application.dependency_overrides.clear()
    get_settings.cache_clear()


async def test_clock_advance_requires_a_token(dev_client) -> None:
    response = await dev_client.post("/dev/clock/advance", json={"seconds": 60})

    assert response.status_code == 401
