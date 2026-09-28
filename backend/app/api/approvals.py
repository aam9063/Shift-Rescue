"""Approval endpoints (spec §7.5): list + manager decisions.

Decisions change domain state (assign shifts, notify employees), so they run
in the worker: the API validates, enqueues `apply_approval_decision` and
answers 202. Enqueue failure is a loud 500.
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ManagerPrincipal, current_manager, get_db
from app.db.models import ApprovalRequest, Employee, Manager, Offer, RescueCase, Shift
from app.schemas.dashboard import (
    ApprovalContextOut,
    ApprovalRequestOut,
    iso_utc,
)
from app.workers.tasks import apply_approval_decision

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

logger = structlog.get_logger(__name__)

_KIND_DETAIL = {
    "overtime": "Overtime needed to cover the shift",
    "partial_coverage": "Partial coverage of the shift",
    "schedule_change": "Proposed schedule change",
    "cancel_rescue": "Request to cancel the rescue",
}


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@router.get("", response_model=list[ApprovalRequestOut])
async def list_approvals(
    status_filter: str | None = Query(default=None, alias="status"),
    location_id: str | None = None,
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> list[ApprovalRequestOut]:
    query = (
        select(ApprovalRequest, Offer, RescueCase, Shift, Employee.full_name, Manager.name)
        .join(RescueCase, ApprovalRequest.rescue_id == RescueCase.id)
        .outerjoin(Shift, RescueCase.shift_id == Shift.id)
        .outerjoin(Offer, ApprovalRequest.offer_id == Offer.id)
        .outerjoin(Employee, Offer.employee_id == Employee.id)
        .outerjoin(Manager, ApprovalRequest.decided_by == Manager.id)
        .order_by(ApprovalRequest.created_at.desc())
    )
    if status_filter:
        query = query.where(ApprovalRequest.status == status_filter)
    if location_id:
        query = query.where(RescueCase.location_id == location_id)
    rows = (await session.execute(query)).all()

    result: list[ApprovalRequestOut] = []
    for approval, offer, case, shift, employee_name, decider_name in rows:
        detail = _KIND_DETAIL.get(approval.kind)
        if offer is not None and offer.proposed_start is not None:
            start = _as_utc(offer.proposed_start).strftime("%H:%M")
            end = (
                _as_utc(offer.proposed_end).strftime("%H:%M")
                if offer.proposed_end is not None
                else "?"
            )
            detail = f"Counter-proposal: {start}-{end}"
        result.append(
            ApprovalRequestOut(
                id=approval.id,
                rescueId=approval.rescue_id,
                kind=approval.kind,
                status=approval.status,
                requestedAt=iso_utc(approval.created_at),
                decidedBy=decider_name,
                decidedAt=iso_utc(approval.decided_at)
                if approval.decided_at is not None
                else None,
                expiresAt=iso_utc(offer.expires_at) if offer is not None else None,
                context=ApprovalContextOut(
                    employeeName=employee_name
                    or (f"Employee {case.absent_employee_id}" if case else "Unknown"),
                    shiftTime=f"{_as_utc(shift.starts_at).strftime('%H:%M')}-"
                    f"{_as_utc(shift.ends_at).strftime('%H:%M')}"
                    if shift is not None
                    else "—",
                    detail=detail,
                ),
            )
        )
    return result


async def _approval_or_404(session: AsyncSession, approval_id: str) -> None:
    approval = (
        await session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
        )
    ).scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")


async def _enqueue_decision(
    approval_id: str,
    decision: str,
    principal: ManagerPrincipal,
) -> None:
    """Enqueue the decision or raise a loud 500 (the worker owns the domain)."""
    try:
        apply_approval_decision.delay(approval_id, decision, principal.manager_id)
    except Exception as error:
        logger.error(
            "approval_enqueue_failed",
            approval_id=approval_id,
            decision=decision,
            error=str(error)[:200],
        )
        raise HTTPException(
            status_code=500, detail="Failed to enqueue approval decision"
        ) from error


@router.post("/{approval_id}/approve", status_code=202)
async def approve_approval(
    approval_id: str,
    principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await _approval_or_404(session, approval_id)
    await _enqueue_decision(approval_id, "approved", principal)
    return {"status": "queued", "id": approval_id}


@router.post("/{approval_id}/reject", status_code=202)
async def reject_approval(
    approval_id: str,
    principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await _approval_or_404(session, approval_id)
    await _enqueue_decision(approval_id, "rejected", principal)
    return {"status": "queued", "id": approval_id}
