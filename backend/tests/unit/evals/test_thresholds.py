"""Threshold gate: one source of truth; violations never silently skipped.

The original bug: the eval runner iterated threshold keys (with `_min`
suffixes) but looked them up directly in the report (whose keys have no
suffix), so every lookup was `None` and every gate silently passed.
"""

from pathlib import Path

from app.evals.thresholds import check_thresholds, load_thresholds

COMPLIANT = {
    "intent_accuracy": 0.95,
    "health_detection": 0.98,
    "conditional_time_accuracy": 0.9,
    "avg_latency_ms": 1200.0,
    "avg_cost_usd": 0.01,
}


def test_two_failed_minimums_produce_exactly_two_violations() -> None:
    report = {**COMPLIANT, "intent_accuracy": 0.86, "health_detection": 0.9167}

    violations = check_thresholds(report)

    assert len(violations) == 2
    assert any(
        "intent_accuracy" in v and "0.86" in v and "0.92" in v for v in violations
    )
    assert any(
        "health_detection" in v and "0.9167" in v and "0.95" in v for v in violations
    )


def test_compliant_report_produces_no_violations() -> None:
    assert check_thresholds(COMPLIANT) == []


def test_threshold_naming_unknown_metric_is_a_violation_not_a_pass() -> None:
    # A typo in the YAML (e.g. `intent_acuracy_min`) must never disable the gate:
    # the key has no mapping, so it is reported instead of silently passing.
    violations = check_thresholds(COMPLIANT, {"intent_acuracy_min": 0.92})

    assert len(violations) == 1
    assert "intent_acuracy_min" in violations[0]


def test_mapped_threshold_with_metric_absent_from_report_reports_unknown_metric() -> None:
    # The threshold is mapped, but the report lacks the metric entirely.
    report = {k: v for k, v in COMPLIANT.items() if k != "health_detection"}

    violations = check_thresholds(report, {"health_detection_min": 0.95})

    assert len(violations) == 1
    assert "unknown metric" in violations[0]
    assert "health_detection" in violations[0]


def test_max_threshold_violated_above_and_satisfied_below() -> None:
    limits = {"avg_latency_ms_max": 1000.0, "avg_cost_usd_max": 0.0005}
    above = {**COMPLIANT, "avg_latency_ms": 1051.0, "avg_cost_usd": 0.01}
    below = {**COMPLIANT, "avg_latency_ms": 900.0, "avg_cost_usd": 0.0004}

    violations = check_thresholds(above, limits)

    assert len(violations) == 2
    assert any("avg_latency_ms" in v for v in violations)
    assert any("avg_cost_usd" in v for v in violations)
    assert check_thresholds(below, limits) == []


def test_missing_metric_value_does_not_pass_silently() -> None:
    incomplete = {k: v for k, v in COMPLIANT.items() if k != "health_detection"}

    violations = check_thresholds(incomplete)

    assert any("health_detection" in v for v in violations)


def test_non_numeric_metric_value_does_not_pass_silently() -> None:
    violations = check_thresholds({**COMPLIANT, "intent_accuracy": "high"})

    assert any("intent_accuracy" in v for v in violations)


def test_default_yaml_loads_the_five_documented_keys() -> None:
    thresholds = load_thresholds()

    assert thresholds == {
        "intent_accuracy_min": 0.92,
        "health_detection_min": 0.95,
        "conditional_time_accuracy_min": 0.80,
        "avg_latency_ms_max": 5000,
        "avg_cost_usd_max": 0.05,
    }


def test_load_thresholds_reads_an_explicit_path(tmp_path: Path) -> None:
    path = tmp_path / "thresholds.yaml"
    path.write_text("intent_accuracy_min: 0.5\n", encoding="utf8")

    assert load_thresholds(path) == {"intent_accuracy_min": 0.5}


def test_threshold_key_without_mapping_is_reported() -> None:
    violations = check_thresholds(COMPLIANT, {"mystery_min": 0.5})

    assert len(violations) == 1
    assert "mystery_min" in violations[0]
