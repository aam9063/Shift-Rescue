"""Summarize the newest golden-set eval report (read-only helper)."""

import glob
import io
import json
import os

path = sorted(glob.glob("evals/reports/interpreter_interpreter_*.json"))[-1]
report = json.load(io.open(path, encoding="utf8"))
print("report:", os.path.basename(path), "| prompt:", report["prompt_version"])
print(
    "metrics:",
    {
        key: report[key]
        for key in (
            "intent_accuracy",
            "health_detection",
            "conditional_time_accuracy",
            "avg_latency_ms",
            "avg_cost_usd",
        )
    },
)
print("\nremaining confusion:")
for pair, count in sorted(report["confusion"].items(), key=lambda item: -item[1]):
    print(f"  {pair}: {count}")
print(f"\nfailures ({len(report['failures'])}):")
for failure in report["failures"]:
    print(
        f"  {failure['id']} | {failure['message'][:44]!r} | "
        f"expected={failure['expected']} got={failure['actual']}"
    )
