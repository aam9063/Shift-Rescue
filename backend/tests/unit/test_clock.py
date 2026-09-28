"""Tests for the Clock port (spec §7.3): nothing in the domain calls now()."""

from datetime import UTC, datetime, timedelta

from structlog.testing import capture_logs

from app.core.clock import DEMO_CLOCK_OFFSET_KEY, DemoClock, FakeClock, SystemClock
from app.core.config import Settings


def test_system_clock_returns_aware_utc_now() -> None:
    before = datetime.now(UTC)
    now = SystemClock().now()
    after = datetime.now(UTC)

    assert before <= now <= after
    assert now.tzinfo is not None


def test_fake_clock_starts_at_the_given_moment() -> None:
    start = datetime(2026, 10, 3, 6, 45, tzinfo=UTC)
    clock = FakeClock(start)

    assert clock.now() == start


def test_fake_clock_advances_by_deltas() -> None:
    start = datetime(2026, 10, 3, 6, 45, tzinfo=UTC)
    clock = FakeClock(start)

    clock.advance(timedelta(minutes=10))
    assert clock.now() == start + timedelta(minutes=10)

    clock.advance(timedelta(hours=2))
    assert clock.now() == start + timedelta(minutes=10, hours=2)


def test_fake_clock_set_jumps_to_a_moment() -> None:
    clock = FakeClock(datetime(2026, 10, 3, 6, 45, tzinfo=UTC))
    target = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)

    clock.set(target)
    assert clock.now() == target


# --- DemoClock: the shared, Redis-backed demo offset (spec §7.5) --------------


def test_demo_clock_applies_the_shared_offset() -> None:
    clock = DemoClock(lambda key: b"3600" if key == DEMO_CLOCK_OFFSET_KEY else None)

    before = datetime.now(UTC)
    now = clock.now()
    after = datetime.now(UTC)

    assert before + timedelta(hours=1) <= now <= after + timedelta(hours=1)


def test_demo_clock_applies_a_negative_offset() -> None:
    clock = DemoClock(lambda _key: "-60")

    assert abs(clock.now() - (datetime.now(UTC) - timedelta(seconds=60))) < timedelta(seconds=2)


def test_demo_clock_zero_offset_equals_the_system_clock() -> None:
    clock = DemoClock(lambda _key: None)

    assert abs(clock.now() - SystemClock().now()) < timedelta(seconds=1)


def test_demo_clock_missing_key_degrades_with_one_warning() -> None:
    clock = DemoClock(lambda _key: None)

    with capture_logs() as logs:
        first = clock.now()
        second = clock.now()

    assert abs(first - SystemClock().now()) < timedelta(seconds=1)
    assert abs(second - SystemClock().now()) < timedelta(seconds=1)
    warnings = [e for e in logs if e["event"] == "demo_clock_offset_missing"]
    assert len(warnings) == 1  # one warning per reason, never per read


def test_demo_clock_unparseable_value_degrades_with_a_warning() -> None:
    clock = DemoClock(lambda _key: "not-a-number")

    with capture_logs() as logs:
        now = clock.now()

    assert abs(now - SystemClock().now()) < timedelta(seconds=1)
    assert any(e["event"] == "demo_clock_offset_unparseable" for e in logs)


def test_demo_clock_redis_failure_degrades_with_a_warning() -> None:
    def broken(_key: str) -> str:
        raise ConnectionError("redis down")

    clock = DemoClock(broken)

    with capture_logs() as logs:
        now = clock.now()

    assert abs(now - SystemClock().now()) < timedelta(seconds=1)
    assert any(e["event"] == "demo_clock_offset_read_failed" for e in logs)


# --- Settings.demo_clock_enabled ----------------------------------------------


def test_demo_clock_enabled_in_demo_environments() -> None:
    for env in ("local", "test", "demo"):
        assert Settings(_env_file=None, app_env=env).demo_clock_enabled is True


def test_demo_clock_disabled_outside_demo_environments() -> None:
    for env in ("production", "staging", ""):
        assert Settings(_env_file=None, app_env=env).demo_clock_enabled is False
