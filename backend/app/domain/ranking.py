"""Weighted ranking engine for eligible candidates (spec §5.2).

Pure and deterministic. The score is a configurable weighted sum with a
human-readable explanation per component. **Prohibited by design:** no
response history, acceptance rates or any behavioral profiling feeds this
engine (EU AI Act exposure — spec §5.2).
"""

from dataclasses import dataclass

from app.domain.entities import EligibilityResult, Employee, Reason

RANK_EQUITY = "RANK_EQUITY"
RANK_PROXIMITY = "RANK_PROXIMITY"
RANK_PREFERENCE = "RANK_PREFERENCE"
RANK_NO_OVERTIME = "RANK_NO_OVERTIME"


@dataclass(frozen=True)
class RankingWeights:
    equity: float = 0.4
    proximity: float = 0.3
    preference: float = 0.2
    no_overtime: float = 0.1


@dataclass(frozen=True)
class RankedCandidate:
    employee_id: str
    score: float
    requires_approval: bool
    explanations: tuple[Reason, ...] = ()
    eligible: bool = True


def rank_candidates(
    employees: list[Employee],
    results: list[EligibilityResult],
    coverage_counts_14d: dict[str, int],
    location_zone: str,
    weights: RankingWeights | None = None,
    max_coverages_per_14_days: int = 4,
) -> list[RankedCandidate]:
    """Rank eligible candidates; ties break deterministically by employee id."""
    weights = weights or RankingWeights()
    result_by_id = {r.employee_id: r for r in results}

    ranked: list[RankedCandidate] = []
    for employee in employees:
        result = result_by_id.get(employee.id)
        if result is None or not result.eligible:
            continue

        coverages = coverage_counts_14d.get(employee.id, 0)
        equity = 1.0 - min(coverages / max(max_coverages_per_14_days, 1), 1.0)
        proximity = 1.0 if employee.home_zone == location_zone else 0.0
        preference = 1.0 if employee.accepts_extra_shifts else 0.0
        no_overtime = 0.0 if result.requires_approval else 1.0

        score = (
            weights.equity * equity
            + weights.proximity * proximity
            + weights.preference * preference
            + weights.no_overtime * no_overtime
        )

        explanations = (
            Reason(code=RANK_EQUITY, message=f"Equity: {coverages} coverages in 14 days"),
            Reason(
                code=RANK_PROXIMITY,
                message=(
                    f"Proximity: {'lives in' if proximity else 'outside'} {location_zone}"
                ),
            ),
            Reason(
                code=RANK_PREFERENCE,
                message=(
                    "Preference: accepts extra shifts"
                    if preference
                    else "Preference: does not accept extra shifts"
                ),
            ),
            Reason(
                code=RANK_NO_OVERTIME,
                message=(
                    "No overtime needed"
                    if no_overtime
                    else "Assignment requires manager approval (overtime)"
                ),
            ),
        )

        ranked.append(
            RankedCandidate(
                employee_id=employee.id,
                score=round(score, 4),
                requires_approval=result.requires_approval,
                explanations=explanations,
                eligible=result.eligible,
            )
        )

    ranked.sort(key=lambda c: (-c.score, c.employee_id))
    return ranked
