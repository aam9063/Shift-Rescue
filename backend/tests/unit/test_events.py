"""Unit tests for the dashboard event bus (spec §7.5, §9.3, §10).

Hermetic: every Redis interaction goes through fakes — a unit test never
talks to a real broker.
"""

import json

import pytest
from structlog.testing import capture_logs

from app.events import (
    DashboardEvent,
    EventName,
    NoopEventBus,
    RedisEventBus,
    channel_for,
    subscribe,
)

EVENT_CHANNEL = "shift_rescue:events:loc_la_terraza"


def _event(**overrides) -> DashboardEvent:
    base = dict(
        name=EventName.OFFER_ACCEPTED,
        location_id="loc_la_terraza",
        rescue_id="case_1",
        shift_id="shift_1",
        origin="employee:emp_1",
        at="2026-10-03T14:40:00+00:00",
    )
    base.update(overrides)
    return DashboardEvent(**base)


class FakePublisher:
    """Stands in for `redis.asyncio.Redis` on the publish side."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self.fail = False

    async def publish(self, channel: str, payload: str) -> None:
        if self.fail:
            raise OSError("broker down")
        self.published.append((channel, payload))


class FakePubSub:
    def __init__(self, messages: list) -> None:
        self.messages = messages
        self.subscribed: list[str] = []
        self.closed = False
        self.fail_subscribe = False

    async def subscribe(self, channel: str) -> None:
        if self.fail_subscribe:
            raise OSError("broker down")
        self.subscribed.append(channel)

    async def listen(self):
        for message in self.messages:
            yield message

    async def aclose(self) -> None:
        self.closed = True


class FakeSubscriber:
    def __init__(self, messages: list) -> None:
        self._pubsub = FakePubSub(messages)
        self.closed = False

    def pubsub(self) -> FakePubSub:
        return self._pubsub

    async def aclose(self) -> None:
        self.closed = True


# --- serialization ---------------------------------------------------------


def test_channel_for_uses_the_location_key() -> None:
    assert channel_for("loc_la_terraza") == EVENT_CHANNEL


def test_event_json_round_trip() -> None:
    event = _event()
    assert DashboardEvent.from_json(event.to_json()) == event


def test_event_json_carries_exactly_the_six_allowed_fields() -> None:
    # Privacy invariant (spec §10): ids, origin and time — nothing else can
    # ride along because the dataclass is the whole payload.
    payload = json.loads(_event().to_json())
    assert set(payload) == {
        "name",
        "location_id",
        "rescue_id",
        "shift_id",
        "origin",
        "at",
    }


@pytest.mark.parametrize(
    "raw",
    ["not json", "[]", json.dumps({"name": "NOT_A_REAL_EVENT"}), json.dumps({})],
)
def test_from_json_is_total_on_garbage(raw: str) -> None:
    assert DashboardEvent.from_json(raw) is None


def test_from_json_fills_defaults_for_optional_fields() -> None:
    event = DashboardEvent.from_json(
        json.dumps({"name": "RESCUE_OPENED", "location_id": "loc_1"})
    )
    assert event is not None
    assert event.rescue_id is None
    assert event.shift_id is None
    assert event.origin == "system"
    assert event.at  # a timestamp is always present


# --- the buses ---------------------------------------------------------------


async def test_noop_bus_drops_events_without_failing() -> None:
    await NoopEventBus().publish(_event())


async def test_redis_bus_publishes_to_the_location_channel() -> None:
    fake = FakePublisher()
    bus = RedisEventBus("redis://localhost:6379/0", client_factory=lambda: fake)

    await bus.publish(_event())

    assert fake.published == [(EVENT_CHANNEL, _event().to_json())]


async def test_redis_bus_reuses_one_client_and_closes_nothing() -> None:
    fake = FakePublisher()
    calls = {"n": 0}

    def factory() -> FakePublisher:
        calls["n"] += 1
        return fake

    bus = RedisEventBus("redis://localhost:6379/0", client_factory=factory)
    await bus.publish(_event())
    await bus.publish(_event())
    assert calls["n"] == 1


async def test_redis_bus_swallows_a_broker_failure_and_logs() -> None:
    fake = FakePublisher()
    fake.fail = True
    bus = RedisEventBus("redis://localhost:6379/0", client_factory=lambda: fake)

    with capture_logs() as logs:
        await bus.publish(_event())

    assert [log["event"] for log in logs] == ["dashboard_event_publish_failed"]
    # A broken client is dropped so the next event rebuilds the connection.
    await bus.publish(_event())  # must not raise either
    assert fake.published == []


# --- the subscriber ----------------------------------------------------------


async def test_subscribe_yields_parsed_events_and_closes_cleanly() -> None:
    event = _event()
    client = FakeSubscriber(
        [
            {"type": "subscribe"},  # control frame: skipped
            {"type": "message", "data": event.to_json()},
            {"type": "message", "data": "garbage"},  # skipped, never crashes
            {"type": "other", "data": event.to_json()},
        ]
    )
    def factory() -> FakeSubscriber:
        return client

    subscription = await subscribe("redis://x/0", EVENT_CHANNEL, client_factory=factory)
    received = [e async for e in subscription.events()]
    await subscription.close()

    assert client.pubsub().subscribed == [EVENT_CHANNEL]
    assert received == [event]
    assert client.pubsub().closed and client.closed
    assert subscription.closed


async def test_subscribe_raises_when_the_broker_is_down() -> None:
    client = FakeSubscriber([])
    client.pubsub().fail_subscribe = True

    def factory() -> FakeSubscriber:
        return client

    with pytest.raises(OSError):
        await subscribe("redis://x/0", EVENT_CHANNEL, client_factory=factory)

    # The failed subscribe still releases the half-open resources.
    assert client.pubsub().closed and client.closed
