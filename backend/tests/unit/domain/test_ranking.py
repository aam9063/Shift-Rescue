"""Unit tests for the ranking engine (spec §5.2)."""

from app.domain.entities import EligibilityResult, Employee
from app.domain.ranking import RankingWeights, rank_candidates


def emp(employee_id: str, zone: str = "port", accepts: bool = True) -> Employee:
    return Employee(
        id=employee_id,
        roles=["floor"],
        contract_weekly_hours=30,
        max_weekly_hours=40,
        home_zone=zone,
        accepts_extra_shifts=accepts,
        active=True,
    )


def result(
    employee_id: str, eligible: bool = True, requires_approval: bool = False
) -> EligibilityResult:
    return EligibilityResult(
        employee_id=employee_id,
        eligible=eligible,
        requires_approval=requires_approval,
        reasons=(),
    )


def ranked_ids(candidates):
    return [c.employee_id for c in candidates]


# --- equity: fewer recent coverages rank higher ---------------------------------


def test_fewer_recent_coverages_rank_higher() -> None:
    candidates = rank_candidates(
        [emp("a"), emp("b")],
        [result("a"), result("b")],
        coverage_counts_14d={"a": 3, "b": 0},
        location_zone="port",
    )
    assert ranked_ids(candidates) == ["b", "a"]
    equity_b = next(e for e in candidates[0].explanations if e.code == "RANK_EQUITY")
    assert "0 coverages" in equity_b.message


# --- proximity: same home zone ranks higher --------------------------------------


def test_same_home_zone_ranks_higher() -> None:
    candidates = rank_candidates(
        [emp("a", zone="north"), emp("b", zone="port")],
        [result("a"), result("b")],
        coverage_counts_14d={},
        location_zone="port",
    )
    assert ranked_ids(candidates) == ["b", "a"]


# --- preference: accepts extra shifts ranks higher --------------------------------


def test_accepts_extra_shifts_ranks_higher() -> None:
    candidates = rank_candidates(
        [emp("a", accepts=False), emp("b", accepts=True)],
        [result("a"), result("b")],
        coverage_counts_14d={},
        location_zone="port",
    )
    assert ranked_ids(candidates) == ["b", "a"]


# --- no overtime: approval-free candidates rank higher -----------------------------


def test_no_overtime_needed_ranks_higher() -> None:
    candidates = rank_candidates(
        [emp("a"), emp("b")],
        [result("a", requires_approval=True), result("b")],
        coverage_counts_14d={},
        location_zone="port",
    )
    assert ranked_ids(candidates) == ["b", "a"]


# --- weights are configurable -------------------------------------------------------


def test_weights_change_the_ordering() -> None:
    # 'a' has better equity, 'b' has better proximity.
    weights_equity_heavy = RankingWeights(
        equity=10.0, proximity=0.1, preference=0.1, no_overtime=0.1
    )
    weights_proximity_heavy = RankingWeights(
        equity=0.1, proximity=10.0, preference=0.1, no_overtime=0.1
    )

    by_equity = rank_candidates(
        [emp("a", zone="north"), emp("b", zone="port")],
        [result("a"), result("b")],
        coverage_counts_14d={"a": 0, "b": 3},
        location_zone="port",
        weights=weights_equity_heavy,
    )
    by_proximity = rank_candidates(
        [emp("a", zone="north"), emp("b", zone="port")],
        [result("a"), result("b")],
        coverage_counts_14d={"a": 0, "b": 3},
        location_zone="port",
        weights=weights_proximity_heavy,
    )
    assert ranked_ids(by_equity) == ["a", "b"]
    assert ranked_ids(by_proximity) == ["b", "a"]


# --- determinism and filtering -------------------------------------------------------


def test_ties_break_deterministically_by_employee_id() -> None:
    candidates = rank_candidates(
        [emp("z"), emp("a")],
        [result("z"), result("a")],
        coverage_counts_14d={},
        location_zone="port",
    )
    assert ranked_ids(candidates) == ["a", "z"]


def test_ineligible_candidates_are_not_ranked() -> None:
    candidates = rank_candidates(
        [emp("a"), emp("b")],
        [result("a", eligible=False), result("b")],
        coverage_counts_14d={},
        location_zone="port",
    )
    assert ranked_ids(candidates) == ["b"]


def test_scores_explain_each_component() -> None:
    candidates = rank_candidates(
        [emp("a")],
        [result("a")],
        coverage_counts_14d={"a": 1},
        location_zone="port",
    )
    codes = {e.code for e in candidates[0].explanations}
    assert codes == {"RANK_EQUITY", "RANK_PROXIMITY", "RANK_PREFERENCE", "RANK_NO_OVERTIME"}
    assert candidates[0].score > 0
