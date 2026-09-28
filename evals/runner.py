"""Golden-set and scenario eval runner (spec §8).

Usage:
  uv run python evals/runner.py --provider parser        # offline baseline
  uv run python evals/runner.py --provider interpreter   # real model via app.agent.factory (OPENAI_API_KEY by default)
  uv run python evals/runner.py --scenarios              # YAML scenario suite (spec §8.2), headless

Every execution records one `eval_run` row (feature evals-live) so the
dashboard's Evals screen shows the real numbers. The trigger comes from
`EVAL_TRIGGER` (`ci` when set, `manual` otherwise).

The parser baseline is informational: it measures the degraded-mode floor.
Threshold checks only block when a real model is evaluated.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.agent.interpreter import PROMPT_VERSION  # noqa: E402
from app.domain.parser import Intent, parse_message  # noqa: E402
from app.evals.recording import (  # noqa: E402
    record_golden_run,
    record_scenario_run,
)
from app.evals.thresholds import check_thresholds, load_thresholds  # noqa: E402


class LLMInterpreterUnavailable(Exception):
    """The LLM path is not configured; the message names the missing variable."""


GOLDEN = Path(__file__).parent / "golden" / "interpreter_golden.jsonl"
REPORTS = Path(__file__).parent / "reports"


class ParserProvider:
    """Deterministic parser with context resolution (Feature 2 degraded mode)."""

    name = "parser (offline baseline)"

    async def interpret(self, message: str, context: dict) -> dict:
        parsed = parse_message(message)
        has_offers = bool(context.get("pending_offers"))
        mapping = {
            Intent.CONFIRM: "OFFER_ACCEPT" if has_offers else "ABSENCE_CONFIRM",
            Intent.DECLINE: "OFFER_DECLINE" if has_offers else "ABSENCE_DECLINE",
            Intent.ABSENCE_REPORT: "ABSENCE_REPORT",
            Intent.ABSENCE_RETRACT: "ABSENCE_RETRACT",
        }
        return {
            "intent": mapping.get(parsed.intent, "UNCLEAR"),
            "confidence": parsed.confidence,
            "contains_health_details": False,
            "proposed_start": None,
            "proposed_end": None,
        }


class InterpreterProvider:
    """Real-model provider built by the shared factory (app.agent.factory), so
    evals and production resolve the provider identically (ADR-004)."""

    name = "interpreter"

    def __init__(self) -> None:
        from app.agent.factory import build_interpreter, resolve_model_id
        from app.core.config import get_settings

        settings = get_settings()
        self.name = f"interpreter ({resolve_model_id(settings)})"
        self._interpreter = build_interpreter(settings)
        if self._interpreter is None:
            raise LLMInterpreterUnavailable(
                "LLM interpreter is not configured: set OPENAI_API_KEY "
                "(or ANTHROPIC_API_KEY with LLM_PROVIDER=anthropic) in backend/.env"
            )
        # The factory wraps StrandsLLMClient inside MessageInterpreter; the
        # usage record (tokens/cost) lives on the client.
        self._client = getattr(self._interpreter, "_llm", None)

    async def interpret(self, message: str, context: dict) -> dict:
        result = await self._interpreter.interpret(message, context)
        usage = getattr(self._client, "last_usage", None) or {}
        return {
            "intent": result.intent,
            "confidence": result.confidence,
            "contains_health_details": result.contains_health_details,
            "proposed_start": result.proposed_start,
            "proposed_end": result.proposed_end,
            "_latency_ms": usage.get("latency_ms", 0.0),
            "_cost_usd": usage.get("cost_usd", 0.0),
        }


def load_golden() -> list[dict]:
    rows = []
    for line in GOLDEN.read_text(encoding="utf8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def f1_per_intent(expected: list[str], actual: list[str]) -> dict[str, float]:
    labels = set(expected) | set(actual)
    scores = {}
    for label in labels:
        tp = sum(1 for e, a in zip(expected, actual) if e == label and a == label)
        fp = sum(1 for e, a in zip(expected, actual) if e != label and a == label)
        fn = sum(1 for e, a in zip(expected, actual) if e == label and a != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores[label] = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
    return scores


async def run(provider) -> dict:
    golden = load_golden()
    expected_intents: list[str] = []
    actual_intents: list[str] = []
    health_hits = 0
    health_total = 0
    time_hits = 0
    time_total = 0
    latencies: list[float] = []
    costs: list[float] = []
    failures: list[dict] = []

    for row in golden:
        expected = row["expected"]
        started = time.perf_counter()
        actual = await provider.interpret(row["message"], row["context"])
        elapsed_ms = (time.perf_counter() - started) * 1000

        expected_intents.append(expected["intent"])
        actual_intents.append(actual["intent"])

        if expected["contains_health_details"]:
            health_total += 1
            if actual.get("contains_health_details"):
                health_hits += 1

        if expected.get("proposed_start") or expected.get("proposed_end"):
            time_total += 1
            start_ok = (expected.get("proposed_start") or "") in (actual.get("proposed_start") or "")
            end_ok = (expected.get("proposed_end") or "") in (actual.get("proposed_end") or "")
            if start_ok and end_ok:
                time_hits += 1

        if actual["intent"] != expected["intent"]:
            failures.append(
                {
                    "id": row["id"],
                    "message": row["message"],
                    "expected": expected["intent"],
                    "actual": actual["intent"],
                }
            )

        latencies.append(float(actual.get("_latency_ms", elapsed_ms)))
        costs.append(float(actual.get("_cost_usd", 0.0)))

    accuracy = sum(1 for e, a in zip(expected_intents, actual_intents) if e == a) / len(golden)
    return {
        "provider": provider.name,
        "total": len(golden),
        "intent_accuracy": round(accuracy, 4),
        "f1_per_intent": {k: round(v, 3) for k, v in f1_per_intent(expected_intents, actual_intents).items()},
        "health_detection": (
            round(health_hits / health_total, 4) if health_total else None
        ),
        "conditional_time_accuracy": (
            round(time_hits / time_total, 4) if time_total else None
        ),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
        "avg_cost_usd": round(sum(costs) / len(costs), 6),
        "confusion": dict(Counter(f"{e}->{a}" for e, a in zip(expected_intents, actual_intents) if e != a)),
        "failures": failures[:50],
    }


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


SCENARIOS = Path(__file__).parent / "scenarios"


async def run_scenario_suite() -> tuple[list[dict], str, str]:
    """Execute the YAML scenario suite headlessly (spec §8.2).

    Reuses the production harness (`app.evals.runner.run_scenario` over
    `evals/scenarios/*.yaml`) — the same code the pytest suite runs — instead
    of reimplementing it. Returns the per-scenario reports, the git sha and
    the interpreter prompt version (aggregation/recording happen in `main`).
    """
    from app.evals.runner import run_scenario as run_scenario_harness

    try:
        from yaml import safe_load
    except ImportError as error:  # PyYAML is not a declared backend dependency
        raise SystemExit(
            "PyYAML is required for --scenarios; run from the backend venv: "
            "cd backend && uv run python ../evals/runner.py --scenarios"
        ) from error

    results: list[dict] = []
    for path in sorted(SCENARIOS.glob("*.yaml")):
        spec = safe_load(path.read_text(encoding="utf8"))
        result = await run_scenario_harness(spec)
        results.append(result)
        verdict = "PASS" if result["expectations_passed"] else "FAIL"
        print(f"  {result['scenario']}: {verdict}")
    return results, git_sha(), PROMPT_VERSION


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["parser", "interpreter"], default="parser")
    parser.add_argument(
        "--scenarios",
        action="store_true",
        help="run the YAML scenario suite (spec §8.2) instead of the golden set",
    )
    args = parser.parse_args()

    if args.scenarios:
        return await run_and_record_scenarios()

    if args.provider == "interpreter":
        try:
            provider = InterpreterProvider()
        except LLMInterpreterUnavailable as error:
            print(error, file=sys.stderr)
            return 2
    else:
        provider = ParserProvider()
    started_at = datetime.now(UTC)
    report = await run(provider)
    report.update(
        {
            "git_sha": git_sha(),
            "ran_at": datetime.now(UTC).isoformat(),
            "prompt_version": PROMPT_VERSION,
        }
    )

    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS / f"interpreter_{args.provider}_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")

    print(f"Provider : {report['provider']}")
    print(f"Samples  : {report['total']}")
    print(f"Accuracy : {report['intent_accuracy']}")
    print(f"Health   : {report['health_detection']}")
    print(f"Times    : {report['conditional_time_accuracy']}")
    print(f"Failures : {len(report['failures'])} (first 50 kept in report)")

    run_id = await record_golden_run(
        report,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        thresholds_enforced=args.provider != "parser",
        report_path=str(report_path),
        prompt_version=PROMPT_VERSION,
    )
    _print_recorded(run_id)

    if args.provider != "parser":
        violations = check_thresholds(report, load_thresholds())
        if violations:
            print("THRESHOLD VIOLATIONS:", "; ".join(violations), file=sys.stderr)
            return 1
        print("Thresholds met.")
    else:
        print("Baseline run: thresholds not applied (informational).")
    return 0


def _print_recorded(run_id: str | None) -> None:
    """One line saying the run was recorded (with its id), or the honest
    failure line — recording is best-effort and never breaks the run."""
    if run_id is not None:
        print(f"Recorded eval run {run_id}")
    else:
        print("Eval run not recorded (recording failed; see API logs)", file=sys.stderr)


async def run_and_record_scenarios() -> int:
    """Run the scenario suite and record one eval_run row for the suite."""
    print(f"Scenarios ({len(list(SCENARIOS.glob('*.yaml')))} files):")
    started_at = datetime.now(UTC)
    results, sha, prompt_version = await run_scenario_suite()
    finished_at = datetime.now(UTC)

    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = finished_at.strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS / f"scenarios_{stamp}.json"
    report_path.write_text(
        json.dumps(
            {
                "git_sha": sha,
                "ran_at": finished_at.isoformat(),
                "prompt_version": prompt_version,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf8",
    )

    passed = sum(1 for result in results if result["expectations_passed"])
    violations = sum(len(result["invariant_violations"]) for result in results)
    print(f"Scenarios: {passed}/{len(results)} passed, {violations} invariant violations")

    run_id = await record_scenario_run(
        results,
        started_at=started_at,
        finished_at=finished_at,
        git_sha=sha,
        report_path=str(report_path),
        prompt_version=prompt_version,
    )
    _print_recorded(run_id)
    return 0 if passed == len(results) and violations == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
