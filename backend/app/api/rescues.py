"""Rescue endpoints (spec §7.5): list, detail, manual close.

Reads are direct queries; the manual close is domain logic and runs in the
worker (`app.workers.tasks.close_rescue`) — the API only enqueues (202).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ManagerPrincipal, current_manager, get_db
from app.db.models import (
    AuditEvent,
    Employee,
    Offer,
    RescueCase,
    Shift,
)
from app.schemas.dashboard import (
    AuditEventOut,
    CandidateResultOut,
    ExclusionReasonOut,
    OfferOut,
    OfferPreviewOut,
    RescueCaseOut,
    RescueDetailOut,
    ShiftOut,
    iso_utc,
)
from app.workers.tasks import close_rescue_task

router = APIRouter(prefix="/api/rescues", tags=["rescues"])

logger = structlog.get_logger(__name__)

# Offer status -> the compact preview vocabulary the frontend expects.
_PREVIEW_STATUS = {
    "ACCEPTED": "accepted",
    "DECLINED": "declined",
}
# Rescue metrics key that may carry the eligibility snapshot (candidate rows
# with scores and exclusion reasons) when the orchestrator persists it.
CANDIDATES_METRICS_KEY = "candidates"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _preview_status(offer_status: str) -> str:
    return _PREVIEW_STATUS.get(offer_status, "pending")


def _shift_out(shift: Shift, assignee_name: str | None) -> ShiftOut:
    return ShiftOut(
        id=shift.id,
        locationId=shift.location_id,
        role=shift.role,
        startsAt=iso_utc(shift.starts_at),
        endsAt=iso_utc(shift.ends_at),
        assigneeName=assignee_name,
        status=shift.status,
    )


async def _rescue_or_404(session: AsyncSession, rescue_id: str) -> RescueCase:
    case = (
        await session.execute(select(RescueCase).where(RescueCase.id == rescue_id))
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Rescue not found")
    return case


def _rescue_case_out(
    case: RescueCase,
    absent_name: str,
    case_offers: Sequence[tuple[Offer, str | None]],
) -> RescueCaseOut:
    """Compact card shape: previews inline, wave numbers when derivable."""
    return RescueCaseOut(
        id=case.id,
        shiftId=case.shift_id,
        absentEmployeeName=absent_name,
        status=case.status,
        deadlineAt=iso_utc(case.deadline_at),
        openedAt=iso_utc(case.opened_at) if case.opened_at is not None else None,
        waveCurrent=max((offer.wave_number for offer, _ in case_offers), default=None),
        waveTotal=case.metrics.get("wave_total") if case.metrics else None,
        offerPreviews=[
            OfferPreviewOut(employeeName=name or "Unknown", status=_preview_status(offer.status))
            for offer, name in case_offers
        ],
    )


@router.get("", response_model=list[RescueCaseOut])
async def list_rescues(
    status_filter: str | None = Query(default=None, alias="status"),
    location_id: str | None = None,
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> list[RescueCaseOut]:
    query = select(RescueCase).order_by(RescueCase.opened_at.desc())
    if status_filter:
        query = query.where(RescueCase.status == status_filter)
    if location_id:
        query = query.where(RescueCase.location_id == location_id)
    cases = (await session.execute(query)).scalars().all()
    if not cases:
        return []

    case_ids = [case.id for case in cases]
    absent_ids = {case.absent_employee_id for case in cases}
    absences = {
        employee.id: employee.full_name
        for employee in (
            await session.execute(select(Employee).where(Employee.id.in_(absent_ids)))
        ).scalars()
    }
    offers = (
        (
            await session.execute(
                select(Offer, Employee.full_name)
                .outerjoin(Employee, Offer.employee_id == Employee.id)
                .where(Offer.rescue_id.in_(case_ids))
                .order_by(Offer.wave_number, Offer.sent_at)
            )
        )
        .all()
    )
    offers_by_case: dict[str, list[tuple[Offer, str | None]]] = {}
    for offer, name in offers:
        offers_by_case.setdefault(offer.rescue_id, []).append((offer, name))

    return [
        _rescue_case_out(
            case,
            absences.get(case.absent_employee_id, "Unknown"),
            offers_by_case.get(case.id, []),
        )
        for case in cases
    ]


@router.get("/{rescue_id}", response_model=RescueDetailOut)
async def get_rescue(
    rescue_id: str,
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> RescueDetailOut:
    case = await _rescue_or_404(session, rescue_id)

    absent_name = (
        await session.execute(
            select(Employee.full_name).where(Employee.id == case.absent_employee_id)
        )
    ).scalar_one_or_none()
    shift_row = (
        await session.execute(
            select(Shift, Employee.full_name)
            .outerjoin(Employee, Shift.employee_id == Employee.id)
            .where(Shift.id == case.shift_id)
        )
    ).first()
    if shift_row is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    shift, assignee_name = shift_row

    offers = (
        (
            await session.execute(
                select(Offer, Employee.full_name)
                .outerjoin(Employee, Offer.employee_id == Employee.id)
                .where(Offer.rescue_id == case.id)
                .order_by(Offer.wave_number, Offer.sent_at)
            )
        )
        .all()
    )
    events = (
        (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.rescue_id == case.id)
                .order_by(AuditEvent.created_at)
            )
        )
        .scalars()
        .all()
    )

    # Exclusion reasons surface only when the orchestrator stored the
    # eligibility snapshot on the case metrics; nothing is invented here.
    stored_candidates = (case.metrics or {}).get(CANDIDATES_METRICS_KEY)
    if isinstance(stored_candidates, list):
        candidates = [
            CandidateResultOut(
                employeeId=str(entry.get("employeeId", "")),
                name=str(entry.get("name", "")),
                score=float(entry.get("score", 0.0)),
                eligible=bool(entry.get("eligible", False)),
                requiresApproval=bool(entry.get("requiresApproval", False)),
                reasons=[
                    ExclusionReasonOut(
                        code=str(r.get("code", "")), message=str(r.get("message", ""))
                    )
                    for r in entry.get("reasons", [])
                    if isinstance(r, dict)
                ],
            )
            for entry in stored_candidates
            if isinstance(entry, dict)
        ]
    else:
        candidates = [
            CandidateResultOut(
                employeeId=offer.employee_id,
                name=name or "Unknown",
                score=0.0,
                eligible=True,
                requiresApproval=offer.requires_approval,
                reasons=[],
            )
            for offer, name in offers
        ]

    return RescueDetailOut(
        rescue=_rescue_case_out(
            case,
            absent_name or "Unknown",
            [(offer, name) for offer, name in offers],
        ),
        shift=_shift_out(shift, assignee_name),
        timeline=[
            AuditEventOut(
                id=event.id,
                rescueId=event.rescue_id or case.id,
                type=event.type,
                actor=event.actor,
                createdAt=iso_utc(event.created_at),
                interpretedByAi=bool(event.payload.get("interpreted_by_ai"))
                if isinstance(event.payload, dict)
                else None,
            )
            for event in events
        ],
        candidates=candidates,
        offers=[
            OfferOut(
                id=offer.id,
                rescueId=offer.rescue_id,
                employeeName=name or "Unknown",
                waveNumber=offer.wave_number,
                status=offer.status,
                sentAt=iso_utc(offer.sent_at),
                expiresAt=iso_utc(offer.expires_at),
            )
            for offer, name in offers
        ],
    )


@router.post("/{rescue_id}/close", status_code=202)
async def close_rescue(
    rescue_id: str,
    principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Enqueue the manual close; the worker owns the domain transition."""
    await _rescue_or_404(session, rescue_id)
    try:
        close_rescue_task.delay(rescue_id, principal.manager_id)
    except Exception as error:
        logger.error("rescue_close_enqueue_failed", rescue_id=rescue_id, error=str(error)[:200])
        raise HTTPException(status_code=500, detail="Failed to enqueue rescue close") from error
    return {"status": "queued", "id": rescue_id}
