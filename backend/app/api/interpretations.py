"""Interpretation endpoints (spec §7.5/§7.6 screen 8, role `operator`).

The Agent-decisions inspector: filterable rows plus the detail with the
redacted input, the structured output and a Langfuse trace link when one can
be derived. Health details never leave the stored redacted bodies (spec §10).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ManagerPrincipal, get_db, require_role
from app.core.config import Settings, get_settings
from app.db.models import Conversation, Employee, Interpretation, Message
from app.schemas.dashboard import (
    InterpretationDetailOut,
    InterpretationRowOut,
    iso_utc,
)

router = APIRouter(prefix="/api/interpretations", tags=["interpretations"])


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _validation_outcome(confidence: float, settings: Settings) -> str:
    """OK when the interpretation cleared the confidence threshold."""
    return "OK" if confidence >= settings.llm_confidence_threshold else "retry"


def _trace_url(settings: Settings, extracted: dict) -> str | None:
    """Derive a Langfuse trace link only from a stored trace id (no guesses)."""
    trace_id = extracted.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id:
        return None
    return f"{settings.langfuse_host.rstrip('/')}/traces/{trace_id}"


async def _operator_rows(
    session: AsyncSession,
    settings: Settings,
    intent: str | None,
    min_confidence: float | None,
    max_confidence: float | None,
    validation_failed: bool | None,
    model: str | None,
    prompt_version: str | None,
    from_: datetime | None,
    to: datetime | None,
) -> list[tuple[Interpretation, str | None]]:
    query = (
        select(Interpretation, Employee.full_name)
        .join(Message, Interpretation.message_id == Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .outerjoin(Employee, Conversation.employee_id == Employee.id)
        .order_by(Interpretation.created_at.desc())
    )
    if intent:
        query = query.where(Interpretation.intent == intent)
    if min_confidence is not None:
        query = query.where(Interpretation.confidence >= min_confidence)
    if max_confidence is not None:
        query = query.where(Interpretation.confidence <= max_confidence)
    if validation_failed:
        query = query.where(Interpretation.confidence < settings.llm_confidence_threshold)
    if model:
        query = query.where(Interpretation.model == model)
    if prompt_version:
        query = query.where(Interpretation.prompt_version == prompt_version)
    if from_ is not None:
        query = query.where(Interpretation.created_at >= _as_utc(from_))
    if to is not None:
        query = query.where(Interpretation.created_at <= _as_utc(to))
    rows = (await session.execute(query)).all()
    return [(interpretation, employee_name) for interpretation, employee_name in rows]


@router.get("", response_model=list[InterpretationRowOut])
async def list_interpretations(
    _principal: ManagerPrincipal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    intent: str | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    validation_failed: bool | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
) -> list[InterpretationRowOut]:
    rows = await _operator_rows(
        session,
        settings,
        intent,
        min_confidence,
        max_confidence,
        validation_failed,
        model,
        prompt_version,
        from_,
        to,
    )
    return [
        InterpretationRowOut(
            id=interpretation.id,
            time=iso_utc(interpretation.created_at),
            employeeName=employee_name,
            intent=interpretation.intent,
            confidence=interpretation.confidence,
            model=interpretation.model,
            costUsd=interpretation.cost_usd,
            latencyMs=interpretation.latency_ms,
            validation=_validation_outcome(interpretation.confidence, settings),
        )
        for interpretation, employee_name in rows
    ]


@router.get("/{interpretation_id}", response_model=InterpretationDetailOut)
async def get_interpretation(
    interpretation_id: str,
    _principal: ManagerPrincipal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> InterpretationDetailOut:
    row = (
        await session.execute(
            select(Interpretation, Employee.full_name, Message.body_redacted)
            .join(Message, Interpretation.message_id == Message.id)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .outerjoin(Employee, Conversation.employee_id == Employee.id)
            .where(Interpretation.id == interpretation_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Interpretation not found")
    interpretation, employee_name, redacted_body = row
    extracted = interpretation.extracted or {}
    return InterpretationDetailOut(
        id=interpretation.id,
        time=iso_utc(interpretation.created_at),
        employeeName=employee_name,
        intent=interpretation.intent,
        confidence=interpretation.confidence,
        model=interpretation.model,
        costUsd=interpretation.cost_usd,
        latencyMs=interpretation.latency_ms,
        validation=_validation_outcome(interpretation.confidence, settings),
        promptVersion=interpretation.prompt_version,
        inputTokens=interpretation.input_tokens,
        outputTokens=interpretation.output_tokens,
        input=redacted_body,
        output=extracted,
        traceUrl=_trace_url(settings, extracted),
    )
