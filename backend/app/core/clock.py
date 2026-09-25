"""Clock port (spec §7.3): nothing in the domain calls datetime.now() directly."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

import structlog

logger = structlog.get_logger(__name__)

# Single documented Redis key holding the shared demo-clock offset in whole
# seconds (signed). `POST /dev/clock/advance` moves it; every process that
# builds a `DemoClock` reads it, so the API and the worker agree on "now".
DEMO_CLOCK_OFFSET_KEY = "shift_rescue:demo_clock_offset_seconds"


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Current aware moment."""
        ...


class SystemClock:
    """Production clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


# Offset source: given the key, return the raw stored value (str, bytes or
# None) or raise when the backing store is unreachable. Redis clients are
# adapted to this shape by `redis_offset_source`; tests pass plain callables.
OffsetSource = Callable[[str], str | bytes | None]


def redis_offset_source(client: object) -> OffsetSource:
    """Adapt a Redis-like client (`get(key)`) to the offset-source shape."""

    def read(key: str) -> str | bytes | None:
        return client.get(key)  # type: ignore[attr-defined]

    return read


class DemoClock:
    """Demo clock (spec §7.5): system now plus a shared, Redis-backed offset.

    The offset lives under `DEMO_CLOCK_OFFSET_KEY` and is re-read on every
    `now()` call, so `POST /dev/clock/advance` moves every process at once.
    A missing key, an unparseable value or a Redis failure means offset zero
    plus (at most) one warning per reason per clock — the worker must keep
    working with real time, never crash because the demo clock broke.
    """

    def __init__(self, offset_source: OffsetSource) -> None:
        self._offset_source = offset_source
        self._warned: set[str] = set()

    def now(self) -> datetime:
        return datetime.now(UTC) + timedelta(seconds=self.offset_seconds())

    def offset_seconds(self) -> int:
        """Current shared offset in whole seconds (0 when unavailable)."""
        try:
            raw = self._offset_source(DEMO_CLOCK_OFFSET_KEY)
        except Exception as error:  # noqa: BLE001 - any backend failure degrades
            self._warn_once("redis_error", "demo_clock_offset_read_failed", error=str(error)[:200])
            return 0
        if raw is None:
            self._warn_once("missing", "demo_clock_offset_missing")
            return 0
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            return int(raw)
        except ValueError:
            self._warn_once("unparseable", "demo_clock_offset_unparseable", value=str(raw)[:50])
            return 0

    def _warn_once(self, reason: str, event: str, **extra: str) -> None:
        """Log each degradation reason once per clock (keep worker logs sane)."""
        if reason in self._warned:
            return
        self._warned.add(reason)
        logger.warning(event, **extra)


class FakeClock:
    """Deterministic clock for tests and the eval harness."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta

    def set(self, moment: datetime) -> None:
        self._now = moment
