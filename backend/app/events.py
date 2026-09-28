"""Dashboard event bus (spec §7.5, §7.6): the worker publishes, the API relays.

The domain (worker process) publishes one small typed event per meaningful
transition on a Redis pub/sub channel; the API process streams the channel to
the authenticated dashboard sockets. The port keeps both sides testable: the
orchestrator gets a no-op in tests, and the endpoint gets an injected fake.

Privacy invariant (spec §10): a `DashboardEvent` NEVER carries a message
body, a phone number, a name or any health detail — only ids, the origin
label and a timestamp.
"""

import contextlib
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)

# The Redis channel for one location's live events (spec §7.5). The API and
# the worker agree on the key by construction.
CHANNEL_PREFIX = "shift_rescue:events:"


def channel_for(location_id: str) -> str:
    """The pub/sub channel that carries a location's dashboard events."""
    return f"{CHANNEL_PREFIX}{location_id}"


class EventName(StrEnum):
    """Every meaningful domain change the dashboard reacts to (spec §7.6)."""

    RESCUE_OPENED = "RESCUE_OPENED"
    OFFERS_SENT = "OFFERS_SENT"
    OFFER_ACCEPTED = "OFFER_ACCEPTED"
    OFFER_DECLINED = "OFFER_DECLINED"
    CASE_COVERED = "CASE_COVERED"
    CASE_ESCALATED = "CASE_ESCALATED"
    CASE_CLOSED = "CASE_CLOSED"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    MESSAGE_SENT = "MESSAGE_SENT"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_DECIDED = "APPROVAL_DECIDED"


@dataclass(frozen=True)
class DashboardEvent:
    """One domain change, routed by location (spec §7.5).

    Payload rules (spec §10, enforced by construction: these six fields are
    the whole payload): **never** a message body, a phone number, a name or
    a health flag — only ids, the origin label ("system", "agent",
    "employee:<id>", "manager:<id>") and the ISO-8601 moment.
    """

    name: EventName
    location_id: str
    rescue_id: str | None
    shift_id: str | None
    origin: str
    at: str

    def to_json(self) -> str:
        """The exact wire format the socket forwards and the hook parses."""
        return json.dumps(
            {
                "name": self.name.value,
                "location_id": self.location_id,
                "rescue_id": self.rescue_id,
                "shift_id": self.shift_id,
                "origin": self.origin,
                "at": self.at,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "DashboardEvent | None":
        """Parse a subscriber payload; None when malformed or unknown.

        Total on purpose: a bad frame on the channel must never crash the
        relay, it is just skipped.
        """
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        raw_name = data.get("name")
        if not isinstance(raw_name, str):
            return None
        try:
            name = EventName(raw_name)
            location_id = data["location_id"]
        except (KeyError, ValueError):
            return None
        if not isinstance(location_id, str):
            return None

        def _optional_str(key: str) -> str | None:
            value = data.get(key)
            return value if isinstance(value, str) else None

        return cls(
            name=name,
            location_id=location_id,
            rescue_id=_optional_str("rescue_id"),
            shift_id=_optional_str("shift_id"),
            origin=_optional_str("origin") or "system",
            at=_optional_str("at") or datetime.now(UTC).isoformat(),
        )


class EventBus(Protocol):
    """Port the orchestrator publishes through (spec §9.3: best effort)."""

    async def publish(self, event: DashboardEvent) -> None: ...


class NoopEventBus:
    """Test/standalone bus: events are dropped, nothing ever fails."""

    async def publish(self, event: DashboardEvent) -> None:
        return None


def _default_redis(url: str) -> Any:
    # Lazy import: the API and the worker must boot without a broker and
    # without redis installed beyond the Celery dependency (spec §7.4).
    import redis.asyncio as aioredis

    return aioredis.Redis.from_url(url, decode_responses=True)


class RedisEventBus:
    """Worker-side publisher. Failures are logged and swallowed (spec §9.3):
    a down broker must never fail a rescue."""

    def __init__(self, url: str, client_factory: Callable[[], Any] | None = None) -> None:
        self._url = url
        self._client_factory = client_factory or (lambda: _default_redis(url))
        self._client: Any = None

    async def publish(self, event: DashboardEvent) -> None:
        try:
            if self._client is None:
                self._client = self._client_factory()
            await self._client.publish(channel_for(event.location_id), event.to_json())
        except Exception as error:  # the broker never breaks the worker
            logger.warning(
                "dashboard_event_publish_failed",
                name=event.name.value,
                error=str(error)[:200],
            )
            self._client = None  # a broken connection is rebuilt on the next event


class EventSubscription:
    """An active pub/sub subscription on the API side (spec §7.5).

    Iterating `events()` yields parsed `DashboardEvent`s; a dropped broker
    connection ends the iteration quietly so the socket handler cleans up
    (the browser reconnects with backoff) instead of crashing.
    """

    def __init__(self, pubsub: Any, client: Any) -> None:
        self._pubsub = pubsub
        self._client = client
        self.closed = False

    async def events(self) -> AsyncIterator[DashboardEvent]:
        try:
            async for message in self._pubsub.listen():
                if not isinstance(message, dict) or message.get("type") != "message":
                    continue
                event = DashboardEvent.from_json(str(message.get("data") or ""))
                if event is not None:
                    yield event
        except Exception as error:  # broker down or dropped: end the stream quietly
            logger.warning("event_stream_dropped", error=str(error)[:200])
            return

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for closer in (self._pubsub, self._client):
            with contextlib.suppress(Exception):
                await closer.aclose()


async def subscribe(
    url: str,
    channel: str,
    client_factory: Callable[[], Any] | None = None,
) -> EventSubscription:
    """Connect to Redis and subscribe to one channel.

    Raises when the broker cannot be reached (the socket handler answers a
    clear close code instead of hanging); once subscribed, disconnects are
    tolerated by `EventSubscription.events()`.
    """
    factory = client_factory or (lambda: _default_redis(url))
    client = factory()
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(channel)
    except Exception:
        with contextlib.suppress(Exception):
            await pubsub.aclose()
        with contextlib.suppress(Exception):
            await client.aclose()
        raise
    return EventSubscription(pubsub, client)


__all__ = [
    "CHANNEL_PREFIX",
    "DashboardEvent",
    "EventBus",
    "EventName",
    "EventSubscription",
    "NoopEventBus",
    "RedisEventBus",
    "channel_for",
    "subscribe",
]
