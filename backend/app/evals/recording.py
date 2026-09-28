"""Record evaluation runs into `eval_run` (feature evals-live).

One row per runner execution: what ran (model, prompt version, commit,
trigger), when (started/finished), how it went (metrics, threshold verdict,
invariant violations) and where the full report file lives (`report_path`).

Recording is best-effort by contract: it runs *after* an evaluation finished
and must never turn a finished run into a crash, so every failure is logged
and swallowed — the `record_*` helpers return None and the runner keeps
going (a failed run is still recorded, with `passed: false`).
"""

import os
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import EvalRun
from app.db.session import create_engine_and_session
from app.evals.thresholds import check_thresholds, load_thresholds

logger = structlog.get_logger(__name__)

# `EVAL_TRIGGER=ci` marks scheduled runs; anything else (or unset) is manual.
TRIGGER_ENV = "EVAL_TRIGGER"

SUITE_GOLDEN = "golden"
SUITE_SCENARIOS = "scenarios"

# Numeric metrics kept in the row (the bulky failure/confusion lists stay in
# the JSON report file; the row points at it via report_path).
_GOLDEN_METRIC_KEYS = (
    "total",
    "intent_accuracy",
    "f1_per_intent",
    "health_detection",
    "conditional_time_accuracy",
    "avg_latency_ms",
    "avg_cost_usd",
)


def _jsonable(value: Any) -> Any:
    """Make a report JSON-serializable.

    The scenario harness reports carry `datetime` values (the simulated world
    clock), and the JSON columns fail with "Object of type datetime is not JSON
    serializable". Dates become ISO strings, dicts and lists are normalized
    recursively, and anything unknown falls back to `str` rather than losing the
    whole run.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def eval_trigger() -> str:
    """`ci` when the environment flags it (`EVAL_TRIGGER=ci`), `manual` otherwise."""
    return os.environ.get(TRIGGER_ENV, "").strip() or "manual"


def _model_config(report: dict[str, Any]) -> dict[str, str]:
    """Provider and model id from the report's provider label.

    Runner labels look like `interpreter (gpt-4o-mini)` or
    `parser (offline baseline)`; a label without parentheses is kept whole
    as the provider so nothing is invented.
    """
    label = str(report.get("provider", "unknown"))
    provider, _, rest = label.partition("(")
    provider = provider.strip() or label
    model = rest.rstrip(")").strip() if rest else ""
    return {"provider": provider, "model": model or provider}


def _prompt_versions(prompt_version: str | None) -> dict[str, str]:
    return {"interpreter": prompt_version} if prompt_version else {}


async def _persist(
    values: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> str | None:
    """Insert one EvalRun row; log-and-continue on any failure."""
    owned_engine = None
    try:
        factory = session_factory
        if factory is None:
            owned_engine, factory = create_engine_and_session()
        run = EvalRun(**values)
        async with factory() as session:
            session.add(run)
            await session.commit()
            return run.id
    except Exception as error:  # noqa: BLE001 - recording never raises into the runner
        logger.error("eval_run_record_failed", error=str(error)[:200])
        return None
    finally:
        if owned_engine is not None:
            await owned_engine.dispose()


async def record_golden_run(
    report: dict[str, Any],
    *,
    started_at: datetime,
    finished_at: datetime,
    thresholds_enforced: bool,
    report_path: str | None = None,
    prompt_version: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> str | None:
    """Persist one golden-set run.

    `passed` comes from the thresholds file via `check_thresholds` when the
    gate applies (a real model); the offline parser baseline is informational,
    so it is recorded with `passed: true` and `thresholds_enforced: false`.
    """
    thresholds = load_thresholds()
    violations = check_thresholds(report, thresholds) if thresholds_enforced else []
    metrics: dict[str, Any] = {key: report[key] for key in _GOLDEN_METRIC_KEYS if key in report}
    # The threshold the run was judged against travels with the run: the API
    # serves the dashboard from a container that has no access to
    # evals/thresholds.yaml, and a stored verdict should be self-explanatory.
    metrics["threshold"] = float(thresholds["intent_accuracy_min"])
    metrics["suite"] = SUITE_GOLDEN
    metrics["thresholds_enforced"] = thresholds_enforced
    if thresholds_enforced:
        metrics["threshold_violations"] = violations
    return await _persist(
        {
            "git_sha": str(report.get("git_sha", "unknown")),
            "trigger": eval_trigger(),
            "started_at": started_at,
            "finished_at": finished_at,
            "model_config_json": _model_config(report),
            "prompt_versions": _prompt_versions(prompt_version),
            "metrics": metrics,
            "invariant_violations": {},
            "passed": not violations,
            "report_path": report_path,
        },
        session_factory,
    )


async def record_scenario_run(
    results: list[dict[str, Any]],
    *,
    started_at: datetime,
    finished_at: datetime,
    git_sha: str = "unknown",
    report_path: str | None = None,
    prompt_version: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> str | None:
    """Persist one scenario-suite run (per-scenario pass/fail + invariants).

    `results` are the dicts returned by `app.evals.runner.run_scenario`. The
    suite passes only when every scenario passes with zero invariant
    violations.
    """
    scenarios = [
        {
            "id": result.get("scenario", "unknown"),
            "passed": bool(result.get("expectations_passed")),
            "invariant_violations": _jsonable(list(result.get("invariant_violations", []))),
        }
        for result in results
    ]
    flat_violations = [
        f"{scenario['id']}: {violation}"
        for scenario in scenarios
        for violation in scenario["invariant_violations"]
    ]
    metrics = {
        "suite": SUITE_SCENARIOS,
        "scenarios": scenarios,
        "scenarios_passed": sum(1 for scenario in scenarios if scenario["passed"]),
        "scenarios_total": len(scenarios),
    }
    return await _persist(
        {
            "git_sha": git_sha,
            "trigger": eval_trigger(),
            "started_at": started_at,
            "finished_at": finished_at,
            # The harness is hermetic: no external model is involved.
            "model_config_json": {"provider": "harness", "model": "simulated orchestrator"},
            "prompt_versions": _prompt_versions(prompt_version),
            "metrics": metrics,
            "invariant_violations": {"violations": flat_violations},
            "passed": all(scenario["passed"] for scenario in scenarios) and not flat_violations,
            "report_path": report_path,
        },
        session_factory,
    )
