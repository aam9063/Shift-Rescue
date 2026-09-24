"""Alert rules (spec §9.2): pure evaluators consumed by the Ops screen and
Sentry. In MVP they log + surface; paging arrives with production hardening.
"""

from datetime import datetime

STUCK_AFTER_MINUTES = 15
LLM_ERROR_RATE = 0.05
LOW_CONFIDENCE_RATE = 0.20


def rescue_stuck(
    status: str,
    last_event_at: datetime,
    now: datetime,
    threshold_minutes: int = STUCK_AFTER_MINUTES,
) -> bool:
    """Rescue in OFFERING/AWAITING_APPROVAL too long without events."""
    if status not in {"OFFERING", "AWAITING_APPROVAL"}:
        return False
    return (now - last_event_at).total_seconds() > threshold_minutes * 60


def llm_error_rate_alert(errors: int, total: int) -> bool:
    if total == 0:
        return False
    return errors / total > LLM_ERROR_RATE


def low_confidence_alert(low: int, total: int) -> bool:
    if total == 0:
        return False
    return low / total > LOW_CONFIDENCE_RATE


def delivery_failure_alert(failed: int) -> bool:
    return failed > 0


def cost_alert(cost_usd: float, threshold_usd: float) -> bool:
    return cost_usd > threshold_usd
