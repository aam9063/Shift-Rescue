"""Unit tests for the deterministic eligibility engine (spec §5.1)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.eligibility import evaluate_eligibility
from app.domain.entities import (
    AvailabilityBlock,
    Employee,
    RescueSettings,
    ShiftSlot,
)

MADRID = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 10, 3, 6, 45, tzinfo=MADRID)


def shift(
    starts_at: datetime,
    ends_at: datetime,
    role: str = "floor",
    employee_id: str | None = None,
) -> ShiftSlot:
    return ShiftSlot(
        id="target" if employee_id is None else f"shift_{employee_id}",
        location_id="loc",
        role=role,
        starts_at=starts_at,
        ends_at=ends_at,
        employee_id=employee_id,
    )


def employee(
    employee_id: str = "emp_1",
    roles: list[str] | None = None,
    contract: int = 30,
    max_hours: int = 40,
    accepts_extra: bool = True,
    active: bool = True,
) -> Employee:
    return Employee(
        id=employee_id,
        roles=roles or ["floor"],
        contract_weekly_hours=contract,
        max_weekly_hours=max_hours,
        home_zone="port",
        accepts_extra_shifts=accepts_extra,
        active=active,
    )


TARGET = shift(
    datetime(2026, 10, 3, 15, 0, tzinfo=MADRID),
    datetime(2026, 10, 3, 23, 0, tzinfo=MADRID),
)


def codes(result) -> set[str]:
    return {r.code for r in result.reasons}


def evaluate(target, employees, schedule=(), blocks=(), coverage_counts=None, now=NOW):
    return evaluate_eligibility(
        target,
        employees,
        list(schedule),
        list(blocks),
        dict(coverage_counts or {}),
        RescueSettings(),
        now,
    )


def single_result(**kwargs):
    employee_ = kwargs.pop("employee")
    target = kwargs.pop("target", TARGET)
    return evaluate(target, [employee_], **kwargs)[0]


# --- rule 1: active and not the absent employee -------------------------------


def test_inactive_employee_is_not_eligible() -> None:
    result = single_result(employee=employee(active=False))
    assert not result.eligible
    assert "NOT_ACTIVE" in codes(result)


def test_absent_employee_is_never_eligible() -> None:
    target = shift(
        datetime(2026, 10, 3, 15, 0, tzinfo=MADRID),
        datetime(2026, 10, 3, 23, 0, tzinfo=MADRID),
        employee_id="emp_1",
    )
    result = single_result(employee=employee(), target=target)
    assert not result.eligible
    assert "ABSENT_EMPLOYEE" in codes(result)


# --- rule 2: role match -------------------------------------------------------


def test_role_mismatch_is_not_eligible() -> None:
    result = single_result(employee=employee(roles=["kitchen"]))
    assert not result.eligible
    assert "ROLE_MISMATCH" in codes(result)


def test_matching_role_passes_role_check() -> None:
    result = single_result(employee=employee(roles=["floor", "bar"]))
    assert "ROLE_MISMATCH" not in codes(result)


# --- rule 3: no overlapping shift ---------------------------------------------


def test_overlapping_shift_is_not_eligible() -> None:
    overlapping = shift(
        datetime(2026, 10, 3, 14, 0, tzinfo=MADRID),
        datetime(2026, 10, 3, 22, 0, tzinfo=MADRID),
        employee_id="emp_1",
    )
    result = single_result(employee=employee(), schedule=[overlapping])
    assert not result.eligible
    assert "SHIFT_OVERLAP" in codes(result)


def test_touching_shifts_do_not_overlap() -> None:
    earlier = shift(
        datetime(2026, 10, 3, 7, 0, tzinfo=MADRID),
        datetime(2026, 10, 3, 15, 0, tzinfo=MADRID),
        employee_id="emp_1",
    )
    result = single_result(employee=employee(), schedule=[earlier])
    assert "SHIFT_OVERLAP" not in codes(result)


# --- rule 4: minimum rest ------------------------------------------------------


def test_rest_violation_blocks_eligibility() -> None:
    # Previous shift ends 09:00; target starts 15:00 -> 6h rest < 12h.
    last_night = shift(
        datetime(2026, 10, 2, 23, 0, tzinfo=MADRID),
        datetime(2026, 10, 3, 9, 0, tzinfo=MADRID),
        employee_id="emp_1",
    )
    result = single_result(employee=employee(), schedule=[last_night])
    assert not result.eligible
    assert "REST_VIOLATION" in codes(result)
    rest_reason = next(r for r in result.reasons if r.code == "REST_VIOLATION")
    assert "6.0h" in rest_reason.message


def test_exactly_twelve_hours_rest_is_enough() -> None:
    # Ends 03:00; target starts 15:00 -> exactly 12h rest: boundary is inclusive.
    closing = shift(
        datetime(2026, 10, 2, 19, 0, tzinfo=MADRID),
        datetime(2026, 10, 3, 3, 0, tzinfo=MADRID),
        employee_id="emp_1",
    )
    result = single_result(employee=employee(), schedule=[closing])
    assert "REST_VIOLATION" not in codes(result)


def test_rest_before_next_shift_is_checked_too() -> None:
    # Target ends 23:00; next shift starts next day 08:00 -> 9h rest < 12h.
    next_morning = shift(
        datetime(2026, 10, 4, 8, 0, tzinfo=MADRID),
        datetime(2026, 10, 4, 16, 0, tzinfo=MADRID),
        employee_id="emp_1",
    )
    result = single_result(employee=employee(), schedule=[next_morning])
    assert "REST_VIOLATION" in codes(result)


def test_rest_is_measured_in_absolute_time_across_dst() -> None:
    # DST ends 2026-10-25 (clocks go back): 03:00 CEST -> 02:00 CET.
    # Last shift ends 01:00+02:00 (23:00Z); target starts 12:00+01:00 (11:00Z)
    # -> exactly 12h ABSOLUTE rest. Wall-clock arithmetic would wrongly say 11h
    # and block. Absolute time must win: no rest violation.
    last_shift = shift(
        datetime(2026, 10, 24, 19, 0, tzinfo=MADRID),
        datetime(2026, 10, 25, 1, 0, tzinfo=MADRID),
        employee_id="emp_1",
    )
    dst_target = shift(
        datetime(2026, 10, 25, 12, 0, tzinfo=MADRID),
        datetime(2026, 10, 25, 20, 0, tzinfo=MADRID),
    )
    result = single_result(employee=employee(), target=dst_target, schedule=[last_shift])
    assert "REST_VIOLATION" not in codes(result)


# --- rule 5: unavailable blocks -------------------------------------------------


def test_unavailable_block_blocks_eligibility() -> None:
    block = AvailabilityBlock(
        employee_id="emp_1",
        starts_at=datetime(2026, 10, 3, 12, 0, tzinfo=MADRID),
        ends_at=datetime(2026, 10, 3, 20, 0, tzinfo=MADRID),
        kind="unavailable",
    )
    result = single_result(employee=employee(), blocks=[block])
    assert not result.eligible
    assert "UNAVAILABLE_BLOCK" in codes(result)


def test_preferred_off_block_does_not_block() -> None:
    block = AvailabilityBlock(
        employee_id="emp_1",
        starts_at=datetime(2026, 10, 3, 12, 0, tzinfo=MADRID),
        ends_at=datetime(2026, 10, 3, 20, 0, tzinfo=MADRID),
        kind="preferred_off",
    )
    result = single_result(employee=employee(), blocks=[block])
    assert "UNAVAILABLE_BLOCK" not in codes(result)


# --- rules 6-8: weekly hours, coverages, overtime approval ----------------------


def weekly_schedule(hours: float, employee_id: str = "emp_1") -> list[ShiftSlot]:
    # Split `hours` into 8h shifts inside the target's ISO week (2026-W40:
    # Mon 2026-09-28 .. Sun 2026-10-04).
    from datetime import date, timedelta

    slots: list[ShiftSlot] = []
    remaining = hours
    day = date(2026, 9, 28)
    while remaining > 0:
        hours_today = min(8.0, remaining)
        start = datetime.combine(day, datetime.min.time(), tzinfo=MADRID) + timedelta(hours=6)
        slots.append(
            shift(start, start + timedelta(hours=hours_today), employee_id=employee_id)
        )
        remaining -= hours_today
        day += timedelta(days=1)
    return slots


def test_max_weekly_hours_hard_cap_blocks() -> None:
    # 40h already worked + 8h target = 48h > 40h hard cap.
    result = single_result(
        employee=employee(contract=30, max_hours=40),
        schedule=weekly_schedule(40),
    )
    assert not result.eligible
    assert "MAX_WEEKLY_HOURS" in codes(result)


def test_over_contract_but_under_cap_needs_approval() -> None:
    # 29h worked + 8h target = 37h: over 30h contract, under 40h cap.
    result = single_result(
        employee=employee(contract=30, max_hours=40, accepts_extra=True),
        schedule=weekly_schedule(29),
    )
    assert result.eligible
    assert result.requires_approval
    assert "OVERTIME_APPROVAL" in codes(result)


def test_over_contract_without_accepting_extra_is_not_eligible() -> None:
    result = single_result(
        employee=employee(contract=30, max_hours=40, accepts_extra=False),
        schedule=weekly_schedule(29),
    )
    assert not result.eligible
    assert "DECLINES_EXTRA_SHIFTS" in codes(result)


def test_under_contract_needs_no_approval() -> None:
    result = single_result(
        employee=employee(contract=30, max_hours=40),
        schedule=weekly_schedule(16),
    )
    assert result.eligible
    assert not result.requires_approval


def test_max_coverages_per_14_days_blocks() -> None:
    result = single_result(employee=employee(), coverage_counts={"emp_1": 4})
    assert not result.eligible
    assert "MAX_COVERAGES_14D" in codes(result)


def test_all_reasons_carry_readable_messages() -> None:
    result = single_result(employee=employee(roles=["kitchen"], active=False))
    for reason in result.reasons:
        assert reason.message
        assert reason.message[0].isupper() or reason.message[0].isdigit()
