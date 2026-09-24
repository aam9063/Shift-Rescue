"""Tests for the Clock port (spec §7.3): nothing in the domain calls now()."""

from datetime import UTC, datetime, timedelta

from app.core.clock import FakeClock, SystemClock


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
