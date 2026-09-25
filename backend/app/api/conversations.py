"""Conversation endpoints (spec §7.5/§7.6 screen 7): inbox and chat view.

Message bodies are always the stored redacted ones (spec §10); each inbound
message carries its interpretation summary when one was persisted.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ManagerPrincipal, current_manager, get_db
from app.db.models import (
    Conversation,
    Employee,
    Interpretation,
    Message,
    RescueCase,
    Shift,
)
from app.schemas.dashboard import (
    ConversationMessageOut,
    ConversationOut,
    InterpretationSummaryOut,
    iso_utc,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

ACTIVE_RESCUE_STATUSES = ("OPEN", "OFFERING", "AWAITING_APPROVAL", "ESCALATED")


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _initials(name: str | None) -> str:
    if not name:
        return "?"
    parts = name.split()
    return "".join(part[0] for part in parts[:2]).upper() or "?"


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    location_id: str | None = None,
    employee_id: str | None = None,
    has_rescue: bool | None = None,
    from_: datetime | None = None,
    to: datetime | None = None,
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> list[ConversationOut]:
    query = select(Conversation).order_by(Conversation.last_inbound_at.desc())
    if employee_id is not None:
        query = query.where(Conversation.employee_id == employee_id)
    conversations = (await session.execute(query)).scalars().all()
    if not conversations:
        return []

    conversation_ids = [conversation.id for conversation in conversations]
    employee_ids = {
        conversation.employee_id for conversation in conversations if conversation.employee_id
    }
    employees = {
        employee.id: employee
        for employee in (
            await session.execute(select(Employee).where(Employee.id.in_(employee_ids)))
        ).scalars()
    }
    messages = (
        (
            await session.execute(
                select(Message)
                .where(Message.conversation_id.in_(conversation_ids))
                .order_by(Message.created_at)
            )
        )
        .scalars()
        .all()
    )
    messages_by_conversation: dict[str, list[Message]] = {}
    for message in messages:
        messages_by_conversation.setdefault(message.conversation_id, []).append(message)

    # Latest interpretation per message (drives the intent column and the
    # per-message interpretation summaries).
    interpretations_by_message: dict[str, str] = {}
    all_message_ids = [message.id for message in messages]
    if all_message_ids:
        interpretations = (
            (
                await session.execute(
                    select(Interpretation)
                    .where(Interpretation.message_id.in_(all_message_ids))
                    .order_by(Interpretation.created_at)
                )
            )
            .scalars()
            .all()
        )
        for interpretation in interpretations:  # last write wins per message
            interpretations_by_message[interpretation.message_id] = interpretation.intent

    # Active rescue per employee (drives hasRescue and the rescue label).
    rescues: dict[str, RescueCase] = {}
    if employee_ids:
        cases = (
            (
                await session.execute(
                    select(RescueCase).where(
                        RescueCase.absent_employee_id.in_(employee_ids),
                        RescueCase.status.in_(ACTIVE_RESCUE_STATUSES),
                    )
                )
            )
            .scalars()
            .all()
        )
        for case in cases:
            rescues.setdefault(case.absent_employee_id, case)
    case_shift_ids = {case.shift_id for case in rescues.values()}
    shifts: dict[str, Shift] = {}
    if case_shift_ids:
        for shift in (
            (await session.execute(select(Shift).where(Shift.id.in_(case_shift_ids)))).scalars()
        ):
            shifts[shift.id] = shift

    result: list[ConversationOut] = []
    for conversation in conversations:
        conversation_messages = messages_by_conversation.get(conversation.id, [])
        if not conversation_messages:
            continue
        last = conversation_messages[-1]
        last_at = _as_utc(last.created_at)
        if from_ is not None and last_at < _as_utc(from_):
            continue
        if to is not None and last_at > _as_utc(to):
            continue
        employee = employees.get(conversation.employee_id) if conversation.employee_id else None
        if location_id is not None and (employee is None or employee.location_id != location_id):
            continue

        # Intent of the last inbound message that was interpreted.
        intent = None
        for message in reversed(conversation_messages):
            if message.direction == "inbound":
                intent = interpretations_by_message.get(message.id)
                break

        active_case = (
            rescues.get(conversation.employee_id) if conversation.employee_id else None
        )
        rescue_label = "No rescue"
        if active_case is not None:
            active_shift = shifts.get(active_case.shift_id)
            start = _as_utc(active_shift.starts_at).strftime("%H:%M") if active_shift else "?"
            role = active_shift.role if active_shift else "Shift"
            rescue_label = f"{role.capitalize()} {start}"
        if has_rescue is not None and (active_case is not None) != has_rescue:
            continue

        result.append(
            ConversationOut(
                id=conversation.id,
                employeeId=conversation.employee_id,
                employeeName=employee.full_name if employee else None,
                initials=_initials(employee.full_name if employee else None),
                lastMessage=last.body_redacted,
                lastMessageAt=iso_utc(last.created_at),
                intent=intent,
                hasRescue=active_case is not None,
                rescueId=active_case.id if active_case is not None else None,
                rescueLabel=rescue_label,
            )
        )
    return result


@router.get("/{conversation_id}/messages", response_model=list[ConversationMessageOut])
async def list_messages(
    conversation_id: str,
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> list[ConversationMessageOut]:
    conversation = (
        await session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = (
        (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )
        )
        .scalars()
        .all()
    )
    if not messages:
        return []
    interpretations = {
        interpretation.message_id: interpretation
        for interpretation in (
            await session.execute(
                select(Interpretation).where(
                    Interpretation.message_id.in_([m.id for m in messages])
                )
            )
        ).scalars()
    }
    return [
        ConversationMessageOut(
            id=message.id,
            **{"from": "employee" if message.direction == "inbound" else "assistant"},
            text=message.body_redacted,
            createdAt=iso_utc(message.created_at),
            interpretation=(
                InterpretationSummaryOut(
                    intent=interpretations[message.id].intent,
                    confidence=interpretations[message.id].confidence,
                    model=interpretations[message.id].model,
                )
                if message.direction == "inbound" and message.id in interpretations
                else None
            ),
        )
        for message in messages
    ]
