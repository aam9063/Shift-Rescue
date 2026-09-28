"""Eval run endpoints (feature evals-live): operator-only, summary composition.

Covers auth (401 without token, 403 for a manager role), the newest-first
bounded list, the 404 detail, and the summary composed from several rows:
accuracy history oldest->newest, per-scenario results from the newest
scenario run, model comparison grouped by model, threshold from the gates
file — plus the empty-but-valid summary with no rows.
"""

from datetime import UTC, datetime, timedelta

from app.db.models import EvalRun
from tests.conftest import MANAGER_ID, OPERATOR_ID, auth_headers

BASE = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=2)


def _golden_row(
    run_id: str,
    *,
    minutes_ago: int,
    accuracy: float,
    model: str,
    passed: bool | None = None,
) -> EvalRun:
    created = BASE - timedelta(minutes=minutes_ago)
    return EvalRun(
        id=run_id,
        git_sha=f"sha_{run_id}",
        trigger="manual",
        started_at=created,
        finished_at=created + timedelta(minutes=3),
        model_config_json={"provider": "interpreter", "model": model},
        prompt_versions={"interpreter": "v3"},
        metrics={
            "suite": "golden",
            "total": 155,
            "intent_accuracy": accuracy,
            "health_detection": 1.0,
            "conditional_time_accuracy": 0.95,
            "avg_latency_ms": 900.0,
            "avg_cost_usd": 0.001,
            "thresholds_enforced": True,
            "threshold_violations": [],
            # Recorded by the recorder: the gate this run was judged against
            # travels with the run (the API container has no access to
            # evals/thresholds.yaml).
            "threshold": 0.92,
        },
        invariant_violations={},
        passed=accuracy >= 0.92 if passed is None else passed,
        report_path="evals/reports/x.json",
        created_at=created,
    )


def _scenario_row(run_id: str, *, minutes_ago: int, failing: bool) -> EvalRun:
    created = BASE - timedelta(minutes=minutes_ago)
    scenarios = [
        {"id": "quick_coverage", "passed": True, "invariant_violations": []},
        {
            "id": "no_candidates",
            "passed": not failing,
            "invariant_violations": ["INV1: two ACCEPTED offers"] if failing else [],
        },
    ]
    return EvalRun(
        id=run_id,
        git_sha=f"sha_{run_id}",
        trigger="ci",
        started_at=created,
        finished_at=created + timedelta(minutes=5),
        model_config_json={"provider": "harness", "model": "simulated orchestrator"},
        prompt_versions={"interpreter": "v3"},
        metrics={
            "suite": "scenarios",
            "scenarios": scenarios,
            "scenarios_passed": 2 - failing,
            "scenarios_total": 2,
        },
        invariant_violations={
            "violations": ["no_candidates: INV1: two ACCEPTED offers"] if failing else []
        },
        passed=not failing,
        report_path="evals/reports/scenarios.json",
        created_at=created,
    )


async def _seed(db, *rows: EvalRun) -> None:
    async with db() as session:
        session.add_all(rows)
        await session.commit()


# --- auth ----------------------------------------------------------------------


async def test_runs_require_a_token(client) -> None:
    response = await client.get("/api/evals/runs")
    assert response.status_code == 401


async def test_runs_require_the_operator_role(client, db) -> None:
    await _seed(db, _golden_row("run_g1", minutes_ago=30, accuracy=0.95, model="model-a"))
    manager = auth_headers(MANAGER_ID, "manager")
    operator = auth_headers(OPERATOR_ID, "operator")
    for path in ("/api/evals/runs", "/api/evals/runs/run_g1", "/api/evals/runs/summary"):
        response = await client.get(path, headers=manager)
        assert response.status_code == 403, path
    # The operator role gets through on the same routes.
    for path in ("/api/evals/runs", "/api/evals/runs/summary"):
        ok = await client.get(path, headers=operator)
        assert ok.status_code == 200, path


# --- list and detail ------------------------------------------------------------


async def test_runs_list_is_newest_first_and_bounded(client, db) -> None:
    await _seed(
        db,
        _golden_row("run_g1", minutes_ago=30, accuracy=0.90, model="model-a"),
        _golden_row("run_g2", minutes_ago=20, accuracy=0.95, model="model-a"),
        _scenario_row("run_s1", minutes_ago=10, failing=False),
    )
    operator = auth_headers(OPERATOR_ID, "operator")
    response = await client.get("/api/evals/runs?limit=2", headers=operator)
    assert response.status_code == 200
    rows = response.json()
    assert [row["id"] for row in rows] == ["run_s1", "run_g2"]
    newest = rows[0]
    assert newest["commit"] == "sha_run_s1"
    assert newest["trigger"] == "ci"
    assert newest["model"] == "simulated orchestrator"
    assert newest["provider"] == "harness"
    assert newest["suite"] == "scenarios"
    assert newest["passed"] is True
    assert newest["violationCount"] == 0
    assert newest["startedAt"].endswith("+00:00")
    assert newest["finishedAt"] is not None
    assert newest["metrics"]["scenarios_total"] == 2

    over_limit = await client.get("/api/evals/runs?limit=500", headers=operator)
    assert over_limit.status_code == 422  # bounded: le=100

    invalid = await client.get("/api/evals/runs?limit=0", headers=operator)
    assert invalid.status_code == 422


async def test_run_detail_and_unknown_id_404(client, db) -> None:
    await _seed(db, _golden_row("run_g1", minutes_ago=30, accuracy=0.95, model="model-a"))
    operator = auth_headers(OPERATOR_ID, "operator")
    response = await client.get("/api/evals/runs/run_g1", headers=operator)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "run_g1"
    assert body["commit"] == "sha_run_g1"
    assert body["promptVersions"] == {"interpreter": "v3"}
    assert body["reportPath"] == "evals/reports/x.json"
    assert body["createdAt"].endswith("+00:00")

    missing = await client.get("/api/evals/runs/run_missing", headers=operator)
    assert missing.status_code == 404


# --- summary composition ----------------------------------------------------------


async def test_summary_composes_history_scenarios_and_models(client, db) -> None:
    await _seed(
        db,
        _golden_row("run_g1", minutes_ago=30, accuracy=0.90, model="model-a"),
        _golden_row("run_g2", minutes_ago=20, accuracy=0.95, model="model-a"),
        _golden_row("run_g3", minutes_ago=15, accuracy=0.93, model="model-b"),
        _scenario_row("run_s1", minutes_ago=10, failing=True),
    )
    operator = auth_headers(OPERATOR_ID, "operator")
    response = await client.get("/api/evals/runs/summary", headers=operator)
    assert response.status_code == 200
    body = response.json()
    assert body["hasRuns"] is True
    # Header verdict/commit: the newest run overall (the failing scenario run).
    assert body["passed"] is False
    assert body["commit"] == "sha_run_s1"
    assert body["ranAgo"].endswith("ago")
    # Accuracy history: golden runs oldest -> newest.
    assert body["accuracyHistory"] == [0.90, 0.95, 0.93]
    assert body["latestAccuracy"] == 0.93  # newest golden run
    assert body["threshold"] == 0.92  # evals/thresholds.yaml intent_accuracy_min
    # Per-scenario results: the newest scenario run, failures included.
    assert body["scenarios"] == [
        {"id": "quick_coverage", "passed": True},
        {"id": "no_candidates", "passed": False},
    ]
    assert body["invariantViolations"] == 1
    # Model comparison: grouped by model, newest run per model.
    assert body["models"] == [
        {"name": "model-a", "accuracy": 0.95, "costPerMessage": "$0.0010"},
        {"name": "model-b", "accuracy": 0.93, "costPerMessage": "$0.0010"},
    ]


async def test_summary_without_runs_is_empty_but_valid(client) -> None:
    response = await client.get(
        "/api/evals/runs/summary", headers=auth_headers(OPERATOR_ID, "operator")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hasRuns"] is False
    assert body["accuracyHistory"] == []
    assert body["scenarios"] == []
    assert body["models"] == []
    assert body["invariantViolations"] == 0
    # No run recorded means no gate was applied, so no threshold is claimed:
    # the screen shows the empty state rather than a number nobody can verify.
    assert body["threshold"] == 0.0
