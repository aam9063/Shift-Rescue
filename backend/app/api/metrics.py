"""Operational metrics (spec §7.5/§9.1-9.2): the Ops screen numbers.

Computed over `interpretation` (LLM cost/latency/confidence), `message`
(delivery failures) and `rescue_case` (stuck rescues: active without audit
events for over 15 minutes). Health details are never part of any metric.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ManagerPrincipal, current_manager, get_db
from app.core.config import Settings, get_settings
from app.db.models import AuditEvent, Conversation, Employee, Interpretation, Message, RescueCase
from app.schemas.dashboard import DailyCostOut, MetricsOut

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

STUCK_AFTER_MINUTES = 15
ACTIVE_RESCUE_STATUSES = ("OPEN", "OFFERING", "AWAITING_APPROVAL", "ESCALATED")
FAILED_DELIVERY = "failed"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _percentile(values: list[int], fraction: float) -> float:
    """Nearest-rank percentile over a small sample (demo scale)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return float(ordered[index])


async def _location_employee_ids(session: AsyncSession, location_id: str) -> list[str]:
    return list(
        (
            await session.execute(select(Employee.id).where(Employee.location_id == location_id))
        ).scalars()
    )


@router.get("", response_model=MetricsOut)
async def get_metrics(
    location_id: str | None = None,
    from_: datetime | None = None,
    to: datetime | None = None,
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MetricsOut:
    # Interpretations: scope through message -> conversation -> employee when a
    # location is requested (interpretations carry no location of their own).
    interpretation_query = select(Interpretation)
    if location_id is not None:
        employee_ids = await _location_employee_ids(session, location_id)
        interpretation_query = (
            interpretation_query.join(Message, Interpretation.message_id == Message.id)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.employee_id.in_(employee_ids or ["-"]))
        )
    if from_ is not None:
        interpretation_query = interpretation_query.where(
            Interpretation.created_at >= _as_utc(from_)
        )
    if to is not None:
        interpretation_query = interpretation_query.where(Interpretation.created_at <= _as_utc(to))
    interpretations = (await session.execute(interpretation_query)).scalars().all()

    costs: dict[str, float] = {}
    for interpretation in interpretations:
        day = _as_utc(interpretation.created_at).date().isoformat()
        costs[day] = costs.get(day, 0.0) + interpretation.cost_usd
    latencies = [interpretation.latency_ms for interpretation in interpretations]
    low_confidence = [
        interpretation
        for interpretation in interpretations
        if interpretation.confidence < settings.llm_confidence_threshold
    ]

    # Delivery failures: outbound messages that could not be delivered.
    delivery_query = select(func.count()).select_from(Message).where(
        Message.delivery_status == FAILED_DELIVERY
    )
    if location_id is not None:
        employee_ids = await _location_employee_ids(session, location_id)
        delivery_query = delivery_query.join(
            Conversation, Message.conversation_id == Conversation.id
        ).where(Conversation.employee_id.in_(employee_ids or ["-"]))
    delivery_failures = (await session.execute(delivery_query)).scalar_one()

    # Stuck rescues: active with no audit events for over 15 minutes.
    stuck_query = select(RescueCase).where(RescueCase.status.in_(ACTIVE_RESCUE_STATUSES))
    if location_id is not None:
        stuck_query = stuck_query.where(RescueCase.location_id == location_id)
    if from_ is not None:
        stuck_query = stuck_query.where(RescueCase.opened_at >= _as_utc(from_))
    if to is not None:
        stuck_query = stuck_query.where(RescueCase.opened_at <= _as_utc(to))
    active_cases = (await session.execute(stuck_query)).scalars().all()
    now = datetime.now(UTC)
    stuck_threshold = now - timedelta(minutes=STUCK_AFTER_MINUTES)
    stuck = 0
    for case in active_cases:
        last_event = (
            await session.execute(
                select(func.max(AuditEvent.created_at)).where(AuditEvent.rescue_id == case.id)
            )
        ).scalar_one()
        last_activity = _as_utc(last_event) if last_event is not None else _as_utc(case.opened_at)
        if last_activity < stuck_threshold:
            stuck += 1

    total = len(interpretations)
    return MetricsOut(
        costPerDay=[
            DailyCostOut(date=day, costUsd=round(cost, 6))
            for day, cost in sorted(costs.items())
        ],
        p50LatencyMs=_percentile(latencies, 0.50),
        p95LatencyMs=_percentile(latencies, 0.95),
        lowConfidencePct=round(100.0 * len(low_confidence) / total, 1) if total else 0.0,
        lowConfidenceTotal=len(low_confidence),
        deliveryFailures=int(delivery_failures),
        stuckRescues=stuck,
    )
