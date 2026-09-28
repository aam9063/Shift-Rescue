"""Recording of eval runs (feature evals-live): one `eval_run` row per run.

Covers the field contract (git sha, trigger, timings, model config, prompt
version, metrics), `passed` derived from the thresholds file, failing runs
recorded as failing, and the best-effort contract: recording never raises
into the runner.
"""

from datetime import UTC, datetime, timedelta

from app.db.models import EvalRun
from app.evals.recording import (
    eval_trigger,
    record_golden_run,
    record_scenario_run,
)

STARTED = datetime(2026, 10, 3, 14, 0, tzinfo=UTC)
FINISHED = STARTED + timedelta(minutes=3)


def _golden_report(**overrides: object) -> dict:
    report = {
        "provider": "interpreter (test-model)",
        "total": 155,
        "intent_accuracy": 0.9935,
        "health_detection": 1.0,
        "conditional_time_accuracy": 0.95,
        "avg_latency_ms": 900.0,
        "avg_cost_usd": 0.001,
        "git_sha": "abc1234",
        "prompt_version": "v3",
    }
    report.update(overrides)
    return report


async def _get_run(db, run_id: str | None) -> EvalRun:
    assert run_id is not None
    async with db() as session:
        row = await session.get(EvalRun, run_id)
    assert row is not None
    return row


async def test_golden_run_records_expected_fields(db, monkeypatch) -> None:
    monkeypatch.setenv("EVAL_TRIGGER", "ci")
    run_id = await record_golden_run(
        _golden_report(),
        started_at=STARTED,
        finished_at=FINISHED,
        thresholds_enforced=True,
        report_path="evals/reports/x.json",
        prompt_version="v3",
        session_factory=db,
    )

    row = await _get_run(db, run_id)
    # SQLite round-trips datetimes as naive UTC walls (see schemas/dashboard.py).
    assert row.started_at.replace(tzinfo=UTC) == STARTED
    assert row.finished_at.replace(tzinfo=UTC) == FINISHED
    assert row.git_sha == "abc1234"
    assert row.model_config_json == {"provider": "interpreter", "model": "test-model"}
    assert row.prompt_versions == {"interpreter": "v3"}
    assert row.report_path == "evals/reports/x.json"
    assert row.metrics["suite"] == "golden"
    assert row.metrics["total"] == 155
    assert row.metrics["intent_accuracy"] == 0.9935
    assert row.metrics["health_detection"] == 1.0
    assert row.metrics["avg_latency_ms"] == 900.0
    assert row.metrics["thresholds_enforced"] is True
    # 0.9935/1.0/0.95 meet every gate in evals/thresholds.yaml.
    assert row.metrics["threshold_violations"] == []
    assert row.passed is True


async def test_passed_derived_from_thresholds_and_failing_run_recorded_failing(
    db, monkeypatch
) -> None:
    monkeypatch.delenv("EVAL_TRIGGER", raising=False)
    assert eval_trigger() == "manual"

    failing_id = await record_golden_run(
        _golden_report(intent_accuracy=0.5),
        started_at=STARTED,
        finished_at=FINISHED,
        thresholds_enforced=True,
        session_factory=db,
    )
    row = await _get_run(db, failing_id)
    assert row.passed is False
    assert row.trigger == "manual"
    assert any("intent_accuracy" in violation for violation in row.metrics["threshold_violations"])


async def test_parser_baseline_is_informational_not_a_failure(db) -> None:
    run_id = await record_golden_run(
        _golden_report(provider="parser (offline baseline)", intent_accuracy=0.7),
        started_at=STARTED,
        finished_at=FINISHED,
        thresholds_enforced=False,
        session_factory=db,
    )
    row = await _get_run(db, run_id)
    assert row.metrics["thresholds_enforced"] is False
    assert "threshold_violations" not in row.metrics
    # No gate applied: nothing failed, so the run is not marked failing.
    assert row.passed is True
    assert row.model_config_json == {"provider": "parser", "model": "offline baseline"}


async def test_scenario_run_records_per_scenario_results_and_invariants(db) -> None:
    results = [
        {
            "scenario": "quick_coverage",
            "expectations_passed": True,
            "invariant_violations": [],
        },
        {
            "scenario": "no_candidates",
            "expectations_passed": False,
            "invariant_violations": ["INV1: two ACCEPTED offers"],
        },
    ]
    run_id = await record_scenario_run(
        results,
        started_at=STARTED,
        finished_at=FINISHED,
        git_sha="abc1234",
        prompt_version="v3",
        session_factory=db,
    )
    row = await _get_run(db, run_id)
    assert row.git_sha == "abc1234"
    assert row.metrics["suite"] == "scenarios"
    assert row.metrics["scenarios_total"] == 2
    assert row.metrics["scenarios_passed"] == 1
    assert row.metrics["scenarios"][0] == {
        "id": "quick_coverage",
        "passed": True,
        "invariant_violations": [],
    }
    assert row.invariant_violations == {
        "violations": ["no_candidates: INV1: two ACCEPTED offers"]
    }
    assert row.passed is False
    assert row.model_config_json == {
        "provider": "harness",
        "model": "simulated orchestrator",
    }


async def test_all_green_scenario_suite_is_passed(db) -> None:
    results = [
        {"scenario": "quick_coverage", "expectations_passed": True, "invariant_violations": []},
        {"scenario": "all_decline", "expectations_passed": True, "invariant_violations": []},
    ]
    run_id = await record_scenario_run(
        results, started_at=STARTED, finished_at=FINISHED, session_factory=db
    )
    row = await _get_run(db, run_id)
    assert row.passed is True
    assert row.invariant_violations == {"violations": []}


async def test_recording_never_raises_into_the_runner(db, monkeypatch) -> None:
    def broken_engine():
        raise RuntimeError("no database")

    monkeypatch.setattr("app.evals.recording.create_engine_and_session", broken_engine)
    run_id = await record_golden_run(
        _golden_report(),
        started_at=STARTED,
        finished_at=FINISHED,
        thresholds_enforced=True,
    )
    assert run_id is None  # logged and swallowed, not raised
