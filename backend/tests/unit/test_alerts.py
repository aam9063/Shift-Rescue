"""Alert rule tests (spec §9.2)."""

from datetime import UTC, datetime, timedelta

from app.observability.alerts import (
    cost_alert,
    delivery_failure_alert,
    llm_error_rate_alert,
    low_confidence_alert,
    rescue_stuck,
)


def test_rescue_stuck_after_fifteen_minutes_without_events() -> None:
    now = datetime(2026, 10, 3, 14, 40, tzinfo=UTC)
    last = now - timedelta(minutes=16)
    assert rescue_stuck("OFFERING", last, now) is True
    assert rescue_stuck("COVERED", last, now) is False  # terminal states don't stall
    assert rescue_stuck("OFFERING", now - timedelta(minutes=5), now) is False


def test_llm_error_rate_alert_above_five_percent() -> None:
    assert llm_error_rate_alert(errors=6, total=100) is True
    assert llm_error_rate_alert(errors=5, total=100) is False
    assert llm_error_rate_alert(errors=1, total=10) is True


def test_low_confidence_alert_above_twenty_percent() -> None:
    assert low_confidence_alert(low=21, total=100) is True
    assert low_confidence_alert(low=20, total=100) is False


def test_delivery_failure_alert_on_any_failure() -> None:
    assert delivery_failure_alert(failed=1) is True
    assert delivery_failure_alert(failed=0) is False


def test_cost_alert_threshold() -> None:
    assert cost_alert(cost_usd=0.06, threshold_usd=0.05) is True
    assert cost_alert(cost_usd=0.04, threshold_usd=0.05) is False
