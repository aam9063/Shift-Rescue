"""Deterministic eligibility engine (spec §5.1).

Pure function; every exclusion carries a stable machine code and a readable
English message. The seven invariants of §5.4 never get relaxed here.

NOTE on datetime arithmetic: CPython returns the *naive* difference when
subtracting two aware datetimes that share the same tzinfo object — wrong
across DST transitions. All durations here are therefore computed on
UTC-normalized datetimes; only comparisons (<) are safe as-is.
"""

from datetime import UTC, datetime, timedelta

from app.domain.entities import (
    AvailabilityBlock,
    EligibilityResult,
    Employee,
    Reason,
    RescueSettings,
    ShiftSlot,
)

UTC = UTC


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC)


def _absolute_seconds(later: datetime, earlier: datetime) -> float:
    """Absolute seconds between two aware moments (DST-safe)."""
    return (_utc(later) - _utc(earlier)).total_seconds()

# Stable reason codes (public contract — screens, evals and tests rely on them)
NOT_ACTIVE = "NOT_ACTIVE"
ABSENT_EMPLOYEE = "ABSENT_EMPLOYEE"
ROLE_MISMATCH = "ROLE_MISMATCH"
SHIFT_OVERLAP = "SHIFT_OVERLAP"
REST_VIOLATION = "REST_VIOLATION"
UNAVAILABLE_BLOCK = "UNAVAILABLE_BLOCK"
MAX_WEEKLY_HOURS = "MAX_WEEKLY_HOURS"
MAX_COVERAGES_14D = "MAX_COVERAGES_14D"
DECLINES_EXTRA_SHIFTS = "DECLINES_EXTRA_SHIFTS"
OVERTIME_APPROVAL = "OVERTIME_APPROVAL"


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open intervals: touching endpoints do not overlap."""
    return a_start < b_end and b_start < a_end


def _rest_violation(
    target: ShiftSlot, employee_shifts: list[ShiftSlot], min_rest: timedelta
) -> Reason | None:
    for other in employee_shifts:
        rest_after = timedelta(seconds=_absolute_seconds(target.starts_at, other.ends_at))
        if timedelta(0) <= rest_after < min_rest:
            hours = rest_after.total_seconds() / 3600
            return Reason(
                code=REST_VIOLATION,
                message=(
                    f"Last shift ended {other.ends_at.strftime('%H:%M')}, only {hours:.1f}h rest"
                ),
            )
        rest_before = timedelta(seconds=_absolute_seconds(other.starts_at, target.ends_at))
        if timedelta(0) <= rest_before < min_rest:
            hours = rest_before.total_seconds() / 3600
            return Reason(
                code=REST_VIOLATION,
                message=(
                    f"Next shift starts {other.starts_at.strftime('%H:%M')}, only {hours:.1f}h rest"
                ),
            )
    return None


def _weekly_hours(employee_shifts: list[ShiftSlot], target: ShiftSlot) -> float:
    """Sum of assigned shift hours inside the target's ISO week (Monday-based)."""
    week_start = _utc(
        (target.starts_at - timedelta(days=target.starts_at.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    )
    week_end = week_start + timedelta(days=7)
    return sum(
        _absolute_seconds(s.ends_at, s.starts_at) / 3600
        for s in employee_shifts
        if _utc(s.starts_at) >= week_start and _utc(s.starts_at) < week_end
    )


def evaluate_eligibility(
    target: ShiftSlot,
    employees: list[Employee],
    schedule: list[ShiftSlot],
    availability_blocks: list[AvailabilityBlock],
    coverage_counts_14d: dict[str, int],
    settings: RescueSettings,
    now: datetime,  # noqa: ARG001 — part of the frozen spec signature
) -> list[EligibilityResult]:
    min_rest = timedelta(hours=settings.min_rest_hours)

    results: list[EligibilityResult] = []
    for employee in employees:
        reasons: list[Reason] = []

        # Rule 1: active and not the absent employee.
        if not employee.active:
            reasons.append(Reason(code=NOT_ACTIVE, message="Employee is not active"))
        if employee.id == target.employee_id:
            reasons.append(Reason(code=ABSENT_EMPLOYEE, message="Employee is the one absent"))

        # Rule 2: role match.
        if target.role not in employee.roles:
            reasons.append(
                Reason(
                    code=ROLE_MISMATCH,
                    message=f"Employee roles {employee.roles} do not include '{target.role}'",
                )
            )

        employee_shifts = [s for s in schedule if s.employee_id == employee.id]

        # Rule 3: no overlapping shift.
        if any(
            _overlaps(target.starts_at, target.ends_at, s.starts_at, s.ends_at)
            for s in employee_shifts
        ):
            reasons.append(Reason(code=SHIFT_OVERLAP, message="Employee has an overlapping shift"))

        # Rule 4: minimum rest before and after.
        rest_reason = _rest_violation(target, employee_shifts, min_rest)
        if rest_reason:
            reasons.append(rest_reason)

        # Rule 5: no overlapping unavailable block.
        if any(
            block.kind == "unavailable"
            and _overlaps(target.starts_at, target.ends_at, block.starts_at, block.ends_at)
            for block in availability_blocks
            if block.employee_id == employee.id
        ):
            reasons.append(
                Reason(
                    code=UNAVAILABLE_BLOCK,
                    message="Employee marked unavailable for this window",
                )
            )

        # Rules 6-8: weekly hours vs contract and hard cap.
        target_hours = _absolute_seconds(target.ends_at, target.starts_at) / 3600
        weekly = _weekly_hours(employee_shifts, target) + target_hours
        hard_cap_reason = weekly > employee.max_weekly_hours
        over_contract = weekly > employee.contract_weekly_hours

        if hard_cap_reason:
            reasons.append(
                Reason(
                    code=MAX_WEEKLY_HOURS,
                    message=(
                        f"Would reach {weekly:.1f}h weekly, "
                        f"over the {employee.max_weekly_hours}h hard cap"
                    ),
                )
            )
        elif over_contract:
            if employee.accepts_extra_shifts:
                reasons.append(
                    Reason(
                        code=OVERTIME_APPROVAL,
                        message=(
                        f"Would reach {weekly:.1f}h weekly, "
                        f"over the {employee.contract_weekly_hours}h contract"
                    ),
                    )
                )
            else:
                reasons.append(
                    Reason(
                        code=DECLINES_EXTRA_SHIFTS,
                        message="Employee does not accept extra shifts",
                    )
                )

        # Rule 7: protection against burning out the usual suspects.
        if coverage_counts_14d.get(employee.id, 0) >= settings.max_coverages_per_14_days:
            reasons.append(
                Reason(
                    code=MAX_COVERAGES_14D,
                    message=(
                        f"Already covered {coverage_counts_14d.get(employee.id, 0)} "
                        "shifts in 14 days"
                    ),
                )
            )

        blocking = [r for r in reasons if r.code not in {OVERTIME_APPROVAL}]
        eligible = not blocking
        requires_approval = eligible and OVERTIME_APPROVAL in {r.code for r in reasons}
        results.append(
            EligibilityResult(
                employee_id=employee.id,
                eligible=eligible,
                requires_approval=requires_approval,
                reasons=tuple(reasons),
            )
        )
    return results
