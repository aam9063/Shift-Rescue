"""T1 smoke: ShiftRescueTarget runs a full rescue scenario hermetically."""

from textwrap import dedent

import pytest
from yaml import safe_load

from app.evals.runner import run_scenario

SCENARIO_YAML = dedent(
    """
    id: quick_coverage
    description: One candidate accepts in wave 1; shift covered.
    now: "2026-10-03T14:40:00+02:00"
    floor_count: 4
    absence:
      employee: emp_01_floor
      message: "me encuentro fatal, hoy no puedo ir"
      origin: employee_message
    personas:
      emp_02_floor:
        - after_minutes: 2
          text: "sí"
    expect:
      final_state: COVERED
      covering_employee_in: [emp_02_floor]
      templates_sent: [absence_confirm, offer, offer_confirmed]
      invariants: all
    """
)


@pytest.mark.asyncio
async def test_quick_coverage_scenario_passes_with_zero_invariant_violations() -> None:
    spec = safe_load(SCENARIO_YAML)

    report = await run_scenario(spec)

    assert report["scenario"] == "quick_coverage"
    assert report["expectations_passed"] is True
    assert report["invariant_violations"] == []
    assert report["final_state"] == "COVERED"
    assert report["covering_employee_id"] == "emp_02_floor"
