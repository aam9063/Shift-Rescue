"""Eval run endpoints (spec §7.5, role `operator`): recorded evaluation runs.

The Evals screen (§7.6 screen 9) consumes the summary; the list and the detail
serve inspection. Nothing here invents data: every field is composed from
recorded `eval_run` rows, the thresholds file, or an explicit empty value —
with no rows the summary is empty-but-valid (`hasRuns: false`).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ManagerPrincipal, get_db, require_role
from app.db.models import EvalRun
from app.evals.recording import SUITE_GOLDEN, SUITE_SCENARIOS
from app.schemas.dashboard import (
    EvalModelComparisonOut,
    EvalRunDetailOut,
    EvalRunOut,
    EvalRunSummaryOut,
    EvalScenarioOut,
    iso_utc,
)

router = APIRouter(prefix="/api/evals", tags=["evals"])

DEFAULT_RUNS_LIMIT = 20
MAX_RUNS_LIMIT = 100
# The screen charts the last 10 golden runs; the summary never needs more.
HISTORY_POINTS = 10
# Upper bound for the rows the summary inspects (demo scale).
SUMMARY_SCAN_LIMIT = 500


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _suite(row: EvalRun) -> str:
    metrics = row.metrics if isinstance(row.metrics, dict) else {}
    suite = metrics.get("suite")
    return suite if isinstance(suite, str) else SUITE_GOLDEN


def _violation_count(row: EvalRun) -> int:
    data = row.invariant_violations if isinstance(row.invariant_violations, dict) else {}
    violations = data.get("violations")
    return len(violations) if isinstance(violations, list) else 0


def _model(row: EvalRun) -> str:
    config = row.model_config_json if isinstance(row.model_config_json, dict) else {}
    return str(config.get("model") or config.get("provider") or "unknown")


def _provider(row: EvalRun) -> str:
    config = row.model_config_json if isinstance(row.model_config_json, dict) else {}
    return str(config.get("provider") or "unknown")


def _metric(row: EvalRun, key: str) -> float | None:
    metrics = row.metrics if isinstance(row.metrics, dict) else {}
    value = metrics.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _flag(row: EvalRun, key: str) -> bool | None:
    """A boolean recorded in the row's metrics (`_metric` only reads numbers)."""
    metrics = row.metrics if isinstance(row.metrics, dict) else {}
    value = metrics.get(key)
    return value if isinstance(value, bool) else None


def _ran_ago(moment: datetime) -> str:
    """Human 'how long ago' for the header; the mock's ranAgo slot."""
    seconds = max(0, int((datetime.now(UTC) - _as_utc(moment)).total_seconds()))
    if seconds < 90:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def _run_out(row: EvalRun) -> EvalRunOut:
    finished = (
        iso_utc(row.finished_at) if row.finished_at is not None else None
    )
    return EvalRunOut(
        id=row.id,
        commit=row.git_sha,
        trigger=row.trigger,
        model=_model(row),
        provider=_provider(row),
        suite=_suite(row),
        startedAt=iso_utc(row.started_at),
        finishedAt=finished,
        passed=row.passed,
        metrics=row.metrics if isinstance(row.metrics, dict) else {},
        violationCount=_violation_count(row),
    )


@router.get("/runs/summary", response_model=EvalRunSummaryOut)
async def get_eval_run_summary(
    _principal: ManagerPrincipal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db),
) -> EvalRunSummaryOut:
    """The Evals screen's whole payload, composed from the recorded rows.

    Accuracy history: the last HISTORY_POINTS golden runs, oldest to newest.
    Scenario results and the invariant count: the newest scenario run. Model
    comparison: golden runs grouped by model, newest run per model. Threshold:
    the gates file (configuration, never invented). With no rows: an
    empty-but-valid summary the screen renders as the empty state.
    """
    rows = (
        (
            await session.execute(
                select(EvalRun)
                .order_by(EvalRun.created_at.desc(), EvalRun.id.desc())
                .limit(SUMMARY_SCAN_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return EvalRunSummaryOut(
            hasRuns=False,
            passed=False,
            commit="",
            ranAgo="",
            accuracyHistory=[],
            # No run recorded means no threshold was applied: the screen shows
            # the empty state rather than a gate that never existed.
            threshold=0.0,
            latestAccuracy=0.0,
            scenarios=[],
            models=[],
            invariantViolations=0,
        )

    newest = rows[0]
    golden_rows = [row for row in rows if _suite(row) == SUITE_GOLDEN]
    # The verdict describes the newest run that was actually judged. The offline
    # parser baseline is informational (thresholds_enforced false) and reporting it
    # as "the latest result" would read as a product failure; a failing scenario
    # run, on the other hand, is exactly what the header must shout about.
    judged_rows = [
        row for row in golden_rows if _flag(row, "thresholds_enforced") is not False
    ]
    judged_any = [row for row in rows if _flag(row, "thresholds_enforced") is not False]
    verdict_row = judged_any[0] if judged_any else newest

    # The container does not carry the repository's evals/thresholds.yaml, so the
    # threshold a run was judged against is read from that run's own metrics. It
    # comes from the golden set, which is the suite the gate applies to: a
    # scenario run carries no threshold and the verdict row may well be one.
    gate_row = judged_rows[0] if judged_rows else (golden_rows[0] if golden_rows else None)
    threshold = float(_metric(gate_row, "threshold") or 0.0) if gate_row is not None else 0.0

    history: list[float] = []
    latest_accuracy = 0.0
    accuracy_rows = judged_rows or golden_rows
    if accuracy_rows:
        for row in reversed(accuracy_rows[:HISTORY_POINTS]):
            accuracy = _metric(row, "intent_accuracy")
            if accuracy is not None:
                history.append(accuracy)
        latest_accuracy = _metric(accuracy_rows[0], "intent_accuracy") or 0.0

    scenarios: list[EvalScenarioOut] = []
    invariant_violations = 0
    scenario_rows = [row for row in rows if _suite(row) == SUITE_SCENARIOS]
    if scenario_rows:
        newest_scenario = scenario_rows[0]
        entries = newest_scenario.metrics.get("scenarios") if isinstance(
            newest_scenario.metrics, dict
        ) else None
        if isinstance(entries, list):
            scenarios = [
                EvalScenarioOut(id=str(entry["id"]), passed=bool(entry["passed"]))
                for entry in entries
                if isinstance(entry, dict) and "id" in entry and "passed" in entry
            ]
        invariant_violations = _violation_count(newest_scenario)

    # Rows arrive newest-first: the first hit per model is that model's
    # latest run (its accuracy and cost are the comparison's values).
    by_model: dict[str, EvalRun] = {}
    for row in golden_rows:
        by_model.setdefault(_model(row), row)
    models = [
        EvalModelComparisonOut(
            name=model,
            accuracy=_metric(row, "intent_accuracy") or 0.0,
            costPerMessage=f"${_metric(row, 'avg_cost_usd') or 0.0:.4f}",
        )
        for model, row in sorted(by_model.items())
    ]

    ran_at = (
        verdict_row.finished_at
        if verdict_row.finished_at is not None
        else verdict_row.created_at
    )
    return EvalRunSummaryOut(
        hasRuns=True,
        passed=verdict_row.passed,
        commit=verdict_row.git_sha,
        ranAgo=_ran_ago(ran_at),
        accuracyHistory=history,
        threshold=threshold,
        latestAccuracy=latest_accuracy,
        scenarios=scenarios,
        models=models,
        invariantViolations=invariant_violations,
    )


@router.get("/runs", response_model=list[EvalRunOut])
async def list_eval_runs(
    limit: int = Query(default=DEFAULT_RUNS_LIMIT, ge=1, le=MAX_RUNS_LIMIT),
    _principal: ManagerPrincipal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db),
) -> list[EvalRunOut]:
    """Recorded runs, newest first, bounded by `limit`."""
    rows = (
        (
            await session.execute(
                select(EvalRun)
                .order_by(EvalRun.created_at.desc(), EvalRun.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [_run_out(row) for row in rows]


@router.get("/runs/{run_id}", response_model=EvalRunDetailOut)
async def get_eval_run(
    run_id: str,
    _principal: ManagerPrincipal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db),
) -> EvalRunDetailOut:
    row = await session.get(EvalRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Eval run not found")
    base = _run_out(row)
    return EvalRunDetailOut(
        **base.model_dump(),
        promptVersions=row.prompt_versions if isinstance(row.prompt_versions, dict) else {},
        invariantViolations=(
            row.invariant_violations if isinstance(row.invariant_violations, dict) else {}
        ),
        reportPath=row.report_path,
        createdAt=iso_utc(row.created_at),
    )
