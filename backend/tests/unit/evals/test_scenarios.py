"""Every spec §8.2 minimum scenario must pass with zero invariant violations."""

from pathlib import Path

import pytest
from yaml import safe_load

from app.evals.runner import run_scenario

SCENARIO_DIR = Path(__file__).parents[4] / "evals" / "scenarios"
SCENARIO_FILES = sorted(SCENARIO_DIR.glob("*.yaml"))


def test_spec_minimum_scenario_set_is_complete() -> None:
    # spec §8.2 minimum scenarios (HRIS failure and LLM-down included).
    assert len(SCENARIO_FILES) >= 14


@pytest.mark.parametrize("scenario_file", SCENARIO_FILES, ids=lambda p: p.stem)
async def test_scenario_passes_with_zero_invariant_violations(scenario_file: Path) -> None:
    spec = safe_load(scenario_file.read_text(encoding="utf8"))

    report = await run_scenario(spec)

    assert report["invariant_violations"] == [], (
        f"{spec['id']}: invariant violations {report['invariant_violations']}"
    )
    assert report["expectations_passed"] is True, (
        f"{spec['id']}: {report['expectation_failures']}"
    )
