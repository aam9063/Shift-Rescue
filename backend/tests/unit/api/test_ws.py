"""Unit tests for the live-event socket (spec §7.5, §7.6, §9.3).

Hermetic: no broker, no real Redis — the subscribe seam is monkeypatched and
the manager check runs on SQLite. The close codes are the contract: the hook
in the dashboard clears the session on 4401 and keeps working otherwise.
"""

import json
import os
import tempfile
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.ws import ws_session_factory
from app.core.config import Settings, get_settings
from app.db.models import Base, Manager
from app.db.seed import DEMO_LOCATION_ID
from app.events import DashboardEvent, EventName
from app.main import create_app
from app.security.tokens import issue_token

MANAGER_ROLE = "manager"


@pytest.fixture()
async def db_factory():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        session.add(
            Manager(
                id="mgr_1",
                name="Demo Manager",
                email="manager@laterraza.demo",
                phone_e164="+34600999001",
                password_hash="x",
                role=MANAGER_ROLE,
                location_ids=[DEMO_LOCATION_ID],
            )
        )
        session.add(
            Manager(
                id="mgr_other",
                name="Other Manager",
                email="other@laterraza.demo",
                phone_e164="+34600999002",
                password_hash="x",
                role=MANAGER_ROLE,
                location_ids=["loc_other"],
            )
        )
        session.add(
            Manager(
                id="op_1",
                name="Demo Operator",
                email="operator@laterraza.demo",
                phone_e164="+34600999003",
                password_hash="x",
                role="operator",
                location_ids=[],
            )
        )
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        app_env="test",
        jwt_secret="test-secret",
        database_url="sqlite+aiosqlite:///unused.db",
        redis_url="redis://broker.invalid:6379/0",
    )


@pytest.fixture()
def app(settings, db_factory):
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[ws_session_factory] = lambda: db_factory
    return application


class FakeSubscription:
    def __init__(self, events: list[DashboardEvent] | None = None) -> None:
        self._events = events or []
        self.closed = False

    async def events(self):
        for event in self._events:
            yield event

    async def close(self) -> None:
        self.closed = True


@pytest.fixture()
def installed():
    """Install a fake subscribe seam; returns a dict with what it saw."""
    seen: dict = {}

    def install(monkeypatch, subscription: FakeSubscription) -> dict:
        from app.api import ws as ws_module

        async def fake_subscribe(url: str, channel: str) -> FakeSubscription:
            seen["url"] = url
            seen["channel"] = channel
            seen["subscription"] = subscription
            return subscription

        monkeypatch.setattr(ws_module, "subscribe", fake_subscribe)
        return seen

    return install


def _event(**overrides) -> DashboardEvent:
    base = dict(
        name=EventName.OFFER_ACCEPTED,
        location_id=DEMO_LOCATION_ID,
        rescue_id="case_1",
        shift_id="shift_1",
        origin="employee:emp_1",
        at="2026-10-03T14:40:00+00:00",
    )
    base.update(overrides)
    return DashboardEvent(**base)


def _connect(client: TestClient, token: str | None, location: str = DEMO_LOCATION_ID):
    query = f"?token={token}" if token is not None else ""
    return client.websocket_connect(f"/ws/locations/{location}{query}")


def _rejects_with(app, monkeypatch, token: str | None, code: int) -> None:
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        _connect(client, token) as websocket,
    ):
        websocket.receive_text()
    assert exc_info.value.code == code


# --- authentication (4401) ---------------------------------------------------


def test_socket_rejects_a_missing_token(app, monkeypatch) -> None:
    _rejects_with(app, monkeypatch, token=None, code=4401)


def test_socket_rejects_a_malformed_token(app, monkeypatch) -> None:
    _rejects_with(app, monkeypatch, token="not-a-jwt", code=4401)


def test_socket_rejects_an_expired_token(app, monkeypatch, settings) -> None:
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": "mgr_1",
            "role": MANAGER_ROLE,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    _rejects_with(app, monkeypatch, token=expired, code=4401)


def test_socket_rejects_a_wrong_role_token(app, monkeypatch, settings) -> None:
    token = issue_token("mgr_1", "employee", settings)[0]
    _rejects_with(app, monkeypatch, token=token, code=4401)


# --- authorization (4403) ----------------------------------------------------


def test_socket_rejects_a_manager_without_rights_on_the_location(
    app, monkeypatch, settings
) -> None:
    token = issue_token("mgr_other", MANAGER_ROLE, settings)[0]
    _rejects_with(app, monkeypatch, token=token, code=4403)


def test_socket_rejects_an_unknown_manager(app, monkeypatch, settings) -> None:
    token = issue_token("mgr_ghost", MANAGER_ROLE, settings)[0]
    _rejects_with(app, monkeypatch, token=token, code=4403)


# --- the happy path ----------------------------------------------------------


def test_socket_forwards_a_published_event_to_a_valid_manager(
    app, monkeypatch, installed, settings
) -> None:
    subscription = FakeSubscription([_event()])
    seen = installed(monkeypatch, subscription)
    token = issue_token("mgr_1", MANAGER_ROLE, settings)[0]

    with TestClient(app) as client, _connect(client, token) as websocket:
        payload = json.loads(websocket.receive_text())

    assert payload == {
        "name": "OFFER_ACCEPTED",
        "location_id": DEMO_LOCATION_ID,
        "rescue_id": "case_1",
        "shift_id": "shift_1",
        "origin": "employee:emp_1",
        "at": "2026-10-03T14:40:00+00:00",
    }
    assert seen["channel"] == f"shift_rescue:events:{DEMO_LOCATION_ID}"
    assert subscription.closed  # the subscription is released on disconnect


def test_socket_lets_the_operator_watch_any_location(
    app, monkeypatch, installed, settings
) -> None:
    installed(monkeypatch, FakeSubscription([]))
    token = issue_token("op_1", "operator", settings)[0]

    with (
        TestClient(app) as client,
        _connect(client, token, location="loc_any") as websocket,
        pytest.raises(WebSocketDisconnect),
    ):
        websocket.receive_text()


def test_socket_relays_only_ids_never_payload_bodies(
    app, monkeypatch, installed, settings
) -> None:
    subscription = FakeSubscription([_event(origin="system")])
    installed(monkeypatch, subscription)
    token = issue_token("mgr_1", MANAGER_ROLE, settings)[0]

    with TestClient(app) as client, _connect(client, token) as websocket:
        raw = websocket.receive_text()

    assert "body" not in raw
    assert "phone" not in raw
    assert set(json.loads(raw)) <= {
        "name",
        "location_id",
        "rescue_id",
        "shift_id",
        "origin",
        "at",
    }


# --- broker down (4503) ------------------------------------------------------


def test_socket_closes_4503_when_the_broker_is_unavailable(
    app, monkeypatch, settings
) -> None:
    from app.api import ws as ws_module

    async def broken_subscribe(url: str, channel: str) -> FakeSubscription:
        raise OSError("broker down")

    monkeypatch.setattr(ws_module, "subscribe", broken_subscribe)

    token = issue_token("mgr_1", MANAGER_ROLE, settings)[0]
    _rejects_with(app, monkeypatch, token=token, code=4503)
