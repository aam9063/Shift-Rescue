"""Quiet hours (spec §5.3): offers are never sent during quiet hours unless
the shift starts within the next 3 hours (partial-coverage window included).
"""

from datetime import datetime, time, timedelta

GRACE_HOURS = 3


def _in_quiet_window(now_time: time, quiet_start: time, quiet_end: time) -> bool:
    if quiet_start <= quiet_end:
        return quiet_start <= now_time < quiet_end
    # Window crosses midnight (e.g. 23:00 -> 07:00).
    return now_time >= quiet_start or now_time < quiet_end


def offers_allowed(
    now: datetime,
    shift_start: datetime,
    quiet_start: time,
    quiet_end: time,
) -> bool:
    remaining = (shift_start - now).total_seconds() / 3600
    if remaining <= GRACE_HOURS:
        return True  # urgent: shift starting within 3h (or already started)
    return not _in_quiet_window(now.astimezone(shift_start.tzinfo).time(), quiet_start, quiet_end)


def next_quiet_end(now: datetime, quiet_end: time) -> datetime:
    """Next moment the quiet window ends, in `now`'s timezone."""
    candidate = now.replace(hour=quiet_end.hour, minute=quiet_end.minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate
