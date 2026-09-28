"""Single source of truth for eval thresholds.

Reads `evals/thresholds.yaml` (the documented gates) and evaluates an eval
report against them. The original bug lived in a duplicate hardcoded copy of
the thresholds: the runner iterated threshold keys (`*_min` suffixes) but
looked them up directly in the report (whose metric keys have no suffix), so
every lookup was `None` and every gate silently passed.

Design notes:
- A threshold that names a metric absent from the report is a VIOLATION,
  never a silent pass — a typo in the YAML can no longer disable a gate.
- The default YAML path is resolved relative to this module, so the loader
  works from any cwd.
- The thresholds file is flat `key: number` pairs, so it is parsed with the
  standard library. PyYAML happens to be installed but is NOT a declared
  backend dependency; depending on it here would rely on a transitive pin.
"""

from pathlib import Path

# Explicit mapping from each threshold key to (report field, direction).
# Any threshold key outside this mapping is itself reported as a violation.
THRESHOLD_FIELDS: dict[str, tuple[str, str]] = {
    "intent_accuracy_min": ("intent_accuracy", "min"),
    "health_detection_min": ("health_detection", "min"),
    "conditional_time_accuracy_min": ("conditional_time_accuracy", "min"),
    "avg_latency_ms_max": ("avg_latency_ms", "max"),
    "avg_cost_usd_max": ("avg_cost_usd", "max"),
}

# backend/app/evals/thresholds.py -> parents[3] is the repository root.
DEFAULT_THRESHOLDS_PATH = Path(__file__).resolve().parents[3] / "evals" / "thresholds.yaml"


def _parse_flat_yaml(text: str) -> dict[str, float]:
    """Parse the flat `key: number` thresholds file with the standard library."""
    thresholds: dict[str, float] = {}
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"cannot parse thresholds line: {raw_line!r}")
        thresholds[key.strip()] = float(value.strip())
    return thresholds


def load_thresholds(path: Path | None = None) -> dict[str, float]:
    """Load the threshold limits from YAML (default: the repo's thresholds file)."""
    target = path or DEFAULT_THRESHOLDS_PATH
    return _parse_flat_yaml(target.read_text(encoding="utf-8"))


def check_thresholds(
    report: dict, thresholds: dict[str, float] | None = None
) -> list[str]:
    """Return one human-readable violation per failing threshold.

    Unknown threshold keys, metrics missing from the report and non-numeric
    metric values are all violations — the gate fails closed, never open.
    """
    if thresholds is None:
        thresholds = load_thresholds()

    violations: list[str] = []
    for key, limit in thresholds.items():
        mapping = THRESHOLD_FIELDS.get(key)
        if mapping is None:
            violations.append(
                f"unknown threshold key '{key}' (no mapping to a report field)"
            )
            continue

        field, direction = mapping
        if field not in report:
            violations.append(
                f"unknown metric for threshold '{key}': report has no '{field}'"
            )
            continue

        value = report[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            violations.append(
                f"non-numeric value for threshold '{key}': "
                f"{field}={value!r} (direction {direction}, limit {limit})"
            )
            continue

        if direction == "min" and value < limit:
            violations.append(f"{field}: {value} < {limit} (threshold {key}, min)")
        elif direction == "max" and value > limit:
            violations.append(f"{field}: {value} > {limit} (threshold {key}, max)")
    return violations
