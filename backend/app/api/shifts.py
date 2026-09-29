"""Shift endpoints (spec §7.5): the manager marks an absence, which opens a rescue.

The manager action is authoritative — no WhatsApp confirmation round trip:
the API validates ownership and state, enqueues the domain change and answers
202 (same shape as the close/approval writes). The worker applies it through
`RescueOrchestrator.mark_absence`, which reuses the confirmed-absence path.
No demo gate here: this is production behaviour (unlike `/dev/*`).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.api.dependencies import ManagerPrincipal, current_manager, get_db
from app.db.models import Manager, RescueCase, Shift
from app.observability.redaction import redact_if_health
from app.workers.tasks import mark_shift_absence_task

router = APIRouter(prefix="/api/shifts", tags=["shifts"])

logger = get_logger(__name__)

# Case statuses where a rescue is still running on the shift (must match the
# orchestrator's redelivery guard in `RescueOrchestrator.mark_absence`).
_LIVE_CASE_STATUSES = ("OPEN", "OFFERING", "AWAITING_APPROVAL", "ESCALATED")


class MarkAbsenceIn(BaseModel):
    """Optional context for the audit trail.

    The reason rides only inside the `ABSENCE_MARKED` audit payload,
    health-redacted before storage (spec §10) and capped; nothing else is
    persisted, and it never becomes a message to anyone.
    """

    reason: str | None = Field(default=None, max_length=200)


async def _shift_or_404(
    session: AsyncSession, shift_id: str, manager_id: str
) -> Shift:
    """The shift when it exists at one of the manager's locations, else 404.

    A shift from another location is indistinguishable from a missing one:
    no existence leak across locations (spec §7.5).
    """
    shift = (
        await session.execute(select(Shift).where(Shift.id == shift_id))
    ).scalar_one_or_none()
    if shift is not None:
        manager = (
            await session.execute(select(Manager).where(Manager.id == manager_id))
        ).scalar_one_or_none()
        if manager is not None and shift.location_id in (manager.location_ids or []):
            return shift
    raise HTTPException(status_code=404, detail="Shift not found")


@router.post("/{shift_id}/absence", status_code=202)
async def mark_shift_absence(
    shift_id: str,
    body: MarkAbsenceIn | None = None,
    principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Enqueue the manager-marked absence; the worker owns the domain change.

    202 after the enqueue, 404 when the shift does not exist or is not at the
    manager's location, 409 when the shift is already absent or already has a
    live rescue — the detail says which, so the dashboard can show it.
    """
    shift = await _shift_or_404(session, shift_id, principal.manager_id)
    if shift.status == "absent":
        raise HTTPException(status_code=409, detail="Shift is already marked absent")
    live = (
        await session.execute(
            select(RescueCase.id).where(
                RescueCase.shift_id == shift_id,
                RescueCase.status.in_(_LIVE_CASE_STATUSES),
            )
        )
    ).first()
    if live is not None:
        raise HTTPException(
            status_code=409, detail="A rescue is already running for this shift"
        )
    reason = redact_if_health(body.reason) if body is not None and body.reason else None
    try:
        mark_shift_absence_task.delay(shift_id, principal.manager_id, reason)
    except Exception as error:
        logger.error(
            "shift_absence_enqueue_failed", shift_id=shift_id, error=str(error)[:200]
        )
        raise HTTPException(
            status_code=500, detail="Failed to enqueue shift absence"
        ) from error
    return {"status": "queued", "id": shift_id}
