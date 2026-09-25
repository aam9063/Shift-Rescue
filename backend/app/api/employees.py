"""Employee endpoints (spec §7.5, extended for the demo simulator, §7.6).

`GET /api/employees` is the list the Simulator screen needs: each employee
with their roles, today's shift window and status, and the id of their
conversation when one exists (so the screen can open the real thread). This
extends the spec's endpoint table for the demo screen and is documented as
such in `docs/runbook.md`.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ManagerPrincipal, current_manager, get_db
from app.db.models import Conversation, Employee, Shift
from app.schemas.dashboard import iso_utc

router = APIRouter(prefix="/api/employees", tags=["employees"])


class EmployeeOut(BaseModel):
    id: str
    displayName: str
    roles: list[str]
    # Today's first shift window and status; null when the employee is not
    # scheduled today.
    shiftStartsAt: str | None = None
    shiftEndsAt: str | None = None
    shiftStatus: str | None = None
    conversationId: str | None = None


@router.get("", response_model=list[EmployeeOut])
async def list_employees(
    location_id: str | None = None,
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> list[EmployeeOut]:
    """List employees with today's shift and conversation id per employee.

    "Today" is the calendar day (UTC) containing the current moment; the
    earliest shift that starts today wins when an employee has several.
    """
    query = select(Employee).order_by(Employee.full_name)
    if location_id is not None:
        query = query.where(Employee.location_id == location_id)
    employees = (await session.execute(query)).scalars().all()
    if not employees:
        return []
    employee_ids = [employee.id for employee in employees]

    now = datetime.now(UTC)
    day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    shifts = (
        (
            await session.execute(
                select(Shift)
                .where(
                    Shift.employee_id.in_(employee_ids),
                    Shift.starts_at >= day_start,
                    Shift.starts_at < day_end,
                )
                .order_by(Shift.starts_at)
            )
        )
        .scalars()
        .all()
    )
    shift_by_employee: dict[str, Shift] = {}
    for shift in shifts:  # earliest start wins (already ordered)
        if shift.employee_id is not None:
            shift_by_employee.setdefault(shift.employee_id, shift)

    # Latest conversation per employee (the screen opens its real thread).
    conversations = (
        (
            await session.execute(
                select(Conversation)
                .where(Conversation.employee_id.in_(employee_ids))
                .order_by(Conversation.created_at)
            )
        )
        .scalars()
        .all()
    )
    conversation_by_employee: dict[str, str] = {
        conversation.employee_id: conversation.id  # last write wins = latest
        for conversation in conversations
        if conversation.employee_id
    }

    return [
        EmployeeOut(
            id=employee.id,
            displayName=employee.full_name,
            roles=list(employee.roles),
            shiftStartsAt=iso_utc(shift.starts_at) if shift else None,
            shiftEndsAt=iso_utc(shift.ends_at) if shift else None,
            shiftStatus=shift.status if shift else None,
            conversationId=conversation_by_employee.get(employee.id),
        )
        for employee, shift in (
            (employee, shift_by_employee.get(employee.id)) for employee in employees
        )
    ]
