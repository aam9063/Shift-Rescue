"""Quiet hours tests (spec §5.3): no offers during quiet hours unless the
shift starts within the next 3 hours."""

from datetime import UTC, datetime, time, timedelta

from app.domain.quiet_hours import next_quiet_end, offers_allowed

QUIET_START = time(23, 0)
QUIET_END = time(7, 0)


def check(now: datetime, shift_in_hours: float) -> bool:
    return offers_allowed(
        now, now + timedelta(hours=shift_in_hours), QUIET_START, QUIET_END
    )


def test_blocked_during_quiet_hours_late_evening() -> None:
    now = datetime(2026, 10, 3, 23, 30, tzinfo=UTC)
    assert check(now, 10) is False  # shift next day 09:30


def test_blocked_during_quiet_hours_early_morning() -> None:
    now = datetime(2026, 10, 4, 3, 0, tzinfo=UTC)
    assert check(now, 9) is False


def test_allowed_outside_quiet_hours() -> None:
    now = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    assert check(now, 10) is True
    now = datetime(2026, 10, 3, 7, 0, tzinfo=UTC)  # quiet window ends at 07:00
    assert check(now, 10) is True


def test_allowed_when_shift_starts_within_three_hours() -> None:
    now = datetime(2026, 10, 3, 23, 30, tzinfo=UTC)
    assert check(now, 2.5) is True  # shift at 02:00, inside the exception
    now = datetime(2026, 10, 3, 22, 0, tzinfo=UTC)
    assert check(now, 3) is True  # exactly 3h: boundary inclusive


def test_blocked_at_boundary_outside_grace() -> None:
    now = datetime(2026, 10, 3, 23, 30, tzinfo=UTC)
    assert check(now, 3.1) is False


def test_next_quiet_end_computes_the_next_07_00() -> None:
    now = datetime(2026, 10, 3, 23, 30, tzinfo=UTC)
    nxt = next_quiet_end(now, QUIET_END)
    assert nxt == datetime(2026, 10, 4, 7, 0, tzinfo=UTC)

    now = datetime(2026, 10, 4, 3, 0, tzinfo=UTC)
    nxt = next_quiet_end(now, QUIET_END)
    assert nxt == datetime(2026, 10, 4, 7, 0, tzinfo=UTC)

    now = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)  # outside quiet: next day
    nxt = next_quiet_end(now, QUIET_END)
    assert nxt == datetime(2026, 10, 5, 7, 0, tzinfo=UTC)
