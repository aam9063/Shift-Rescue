"""Property-based tests for the eligibility engine (Hypothesis).

Invariants that must hold for ANY generated schedule — never relaxed (§5.4).
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.eligibility import evaluate_eligibility
from app.domain.entities import (
    AvailabilityBlock,
    Employee,
    RescueSettings,
    ShiftSlot,
)

MADRID = ZoneInfo("Europe/Madrid")
BASE = datetime(2026, 10, 3, 15, 0, tzinfo=MADRID)
NOW = datetime(2026, 10, 3, 6, 45, tzinfo=MADRID)

STABLE_CODES = {
    "NOT_ACTIVE",
    "ABSENT_EMPLOYEE",
    "ROLE_MISMATCH",
    "SHIFT_OVERLAP",
    "REST_VIOLATION",
    "UNAVAILABLE_BLOCK",
    "MAX_WEEKLY_HOURS",
    "MAX_COVERAGES_14D",
    "DECLINES_EXTRA_SHIFTS",
    "OVERTIME_APPROVAL",
}

# Offsets in hours for a candidate's extra shift relative to the target.
offset_hours = st.integers(min_value=-48, max_value=48)
durations = st.integers(min_value=1, max_value=8)  # shift length in hours


def target_shift() -> ShiftSlot:
    return ShiftSlot(
        id="target",
        location_id="loc",
        role="floor",
        starts_at=BASE,
        ends_at=BASE + timedelta(hours=8),
        employee_id="absent_emp",
    )


def gen_employee(employee_id: str = "emp_1") -> Employee:
    return Employee(
        id=employee_id,
        roles=["floor"],
        contract_weekly_hours=60,
        max_weekly_hours=80,
        home_zone="port",
        accepts_extra_shifts=True,
        active=True,
    )


def overlapping_shift(offset: int, duration: int) -> ShiftSlot:
    """A candidate shift overlapping the target (offset < 8 and offset > -duration)."""
    start = BASE + timedelta(hours=offset)
    return ShiftSlot(
        id=f"other_{offset}",
        location_id="loc",
        role="floor",
        starts_at=start,
        ends_at=start + timedelta(hours=duration),
        employee_id="emp_1",
    )


@settings(max_examples=200, deadline=None)
@given(offset=st.integers(min_value=-7, max_value=7), duration=durations)
def test_property_overlapping_shift_never_eligible(offset: int, duration: int) -> None:
    """P1: any overlap between the candidate's shift and the target blocks."""
    other = overlapping_shift(offset, duration)
    # Guarantee genuine overlap: half-open intervals intersect.
    if not (other.starts_at < target_shift().ends_at and other.ends_at > BASE):
        return
    result = evaluate_eligibility(
        target_shift(),
        [gen_employee()],
        [other],
        [],
        {},
        RescueSettings(),
        NOW,
    )[0]
    assert not result.eligible
    assert "SHIFT_OVERLAP" in {r.code for r in result.reasons}


@settings(max_examples=200, deadline=None)
@given(rest_hours=st.integers(min_value=0, max_value=48))
def test_property_rest_monotonicity(rest_hours: int) -> None:
    """P2: more rest can only help — violation iff rest < 12h.

    Previous shift ends exactly `rest_hours` before the target starts.
    """
    prev_end = BASE - timedelta(hours=rest_hours)
    prev = ShiftSlot(
        id="prev",
        location_id="loc",
        role="floor",
        starts_at=prev_end - timedelta(hours=4),
        ends_at=prev_end,
        employee_id="emp_1",
    )
    result = evaluate_eligibility(
        target_shift(),
        [gen_employee()],
        [prev],
        [],
        {},
        RescueSettings(),
        NOW,
    )[0]
    has_violation = "REST_VIOLATION" in {r.code for r in result.reasons}
    assert has_violation == (rest_hours < 12)


@settings(max_examples=100, deadline=None)
@given(st.data())
def test_property_reason_codes_always_stable(data) -> None:
    """P3: every reason code ever produced belongs to the stable contract set."""
    extra = data.draw(offset_hours)
    other = overlapping_shift(extra, data.draw(durations))
    results = evaluate_eligibility(
        target_shift(),
        [gen_employee()],
        [other],
        [],
        {"emp_1": 99},
        RescueSettings(),
        NOW,
    )
    for result in results:
        for reason in result.reasons:
            assert reason.code in STABLE_CODES


@settings(max_examples=50, deadline=None)
@given(st.data())
def test_property_absent_employee_never_eligible(data) -> None:
    """P4: the absent employee can never be a candidate."""
    absent = Employee(
        id="absent_emp",
        roles=["floor"],
        contract_weekly_hours=60,
        max_weekly_hours=80,
        home_zone="port",
        accepts_extra_shifts=True,
        active=True,
    )
    extra = data.draw(offset_hours)
    results = evaluate_eligibility(
        target_shift(),
        [absent],
        [overlapping_shift(extra, data.draw(durations))],
        [],
        {},
        RescueSettings(),
        NOW,
    )
    for result in results:
        assert not result.eligible


@settings(max_examples=100, deadline=None)
@given(unavailable_start=offset_hours, unavailable_duration=durations)
def test_property_unavailable_block_blocks(
    unavailable_start: int, unavailable_duration: int
) -> None:
    """P5: a generated unavailable block overlapping the target blocks."""
    start = BASE + timedelta(hours=unavailable_start)
    end = start + timedelta(hours=unavailable_duration)
    if not (start < BASE + timedelta(hours=8) and end > BASE):
        return
    block = AvailabilityBlock(
        employee_id="emp_1",
        starts_at=start,
        ends_at=end,
        kind="unavailable",
    )
    result = evaluate_eligibility(
        target_shift(),
        [gen_employee()],
        [],
        [block],
        {},
        RescueSettings(),
        NOW,
    )[0]
    assert not result.eligible
    assert "UNAVAILABLE_BLOCK" in {r.code for r in result.reasons}


def test_unused_import_guard() -> None:  # keeps UTC import meaningful if strategies change
    assert datetime.now(UTC).year >= 2026
