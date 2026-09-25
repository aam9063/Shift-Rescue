"""Golden-set eval runner (spec §8.1).

Usage:
  uv run python evals/runner.py --provider parser        # offline baseline
  uv run python evals/runner.py --provider interpreter   # real model via app.agent.factory (OPENAI_API_KEY by default)

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

from app.domain.parser import Intent, parse_message  # noqa: E402


class LLMInterpreterUnavailable(Exception):
    """The LLM path is not configured; the message names the missing variable."""


GOLDEN = Path(__file__).parent / "golden" / "interpreter_golden.jsonl"
REPORTS = Path(__file__).parent / "reports"
THRESHOLDS = {
    "intent_accuracy_min": 0.92,
    "health_detection_min": 0.95,
    "conditional_time_accuracy_min": 0.80,
}


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


def check_thresholds(report: dict) -> list[str]:
    violations = []
    for key, minimum in THRESHOLDS.items():
        value = report.get(key)
        if value is not None and value < minimum:
            violations.append(f"{key}: {value} < {minimum}")
    return violations


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["parser", "interpreter"], default="parser")
    args = parser.parse_args()

    if args.provider == "interpreter":
        try:
            provider = InterpreterProvider()
        except LLMInterpreterUnavailable as error:
            print(error, file=sys.stderr)
            return 2
    else:
        provider = ParserProvider()
    report = await run(provider)
    report.update(
        {
            "git_sha": git_sha(),
            "ran_at": datetime.now(UTC).isoformat(),
            "prompt_version": "interpreter_v1",
        }
    )

    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    (REPORTS / f"interpreter_{args.provider}_{stamp}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
    )

    print(f"Provider : {report['provider']}")
    print(f"Samples  : {report['total']}")
    print(f"Accuracy : {report['intent_accuracy']}")
    print(f"Health   : {report['health_detection']}")
    print(f"Times    : {report['conditional_time_accuracy']}")
    print(f"Failures : {len(report['failures'])} (first 50 kept in report)")

    if args.provider != "parser":
        violations = check_thresholds(report)
        if violations:
            print("THRESHOLD VIOLATIONS:", "; ".join(violations), file=sys.stderr)
            return 1
        print("Thresholds met.")
    else:
        print("Baseline run: thresholds not applied (informational).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
