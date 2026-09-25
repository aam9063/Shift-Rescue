"""SQLAlchemy-backed mock of the client's HR system (spec §7.3).

The agent accesses the HRIS only through this adapter; the underlying tables
(`employee`, `shift`, `availability_block`) simulate the client's system.
Failure/latency injection arrives with the `resilience` feature.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities import AvailabilityBlock, ShiftSlot
from app.ports import WorkforceAdapter


class HrisError(Exception):
    """Simulated HRIS outage (spec §5.5: retries, then escalate)."""


class MockWorkforceAdapter(WorkforceAdapter):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._pending_assign_failures = 0

    def fail_next_assignments(self, count: int) -> None:
        """Inject `count` consecutive assignment failures (eval scenarios)."""
        self._pending_assign_failures = count

    async def list_employees(self, location_id: str) -> list[dict]:
        from app.db.models import Employee

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(Employee).where(
                        Employee.location_id == location_id, Employee.active
                    )
                )
            ).scalars()
            return [
                {
                    "id": e.id,
                    "location_id": e.location_id,
                    "full_name": e.full_name,
                    "phone_e164": e.phone_e164,
                    "language": e.language,
                    "roles": list(e.roles),
                    "contract_weekly_hours": e.contract_weekly_hours,
                    "max_weekly_hours": e.max_weekly_hours,
                    "home_zone": e.home_zone,
                    "accepts_extra_shifts": e.accepts_extra_shifts,
                    "active": e.active,
                }
                for e in rows
            ]

    async def get_schedule(
        self, location_id: str, from_dt: datetime, to_dt: datetime
    ) -> list[ShiftSlot]:
        from app.db.models import Shift

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(Shift).where(
                        Shift.location_id == location_id,
                        Shift.starts_at >= from_dt,
                        Shift.starts_at < to_dt,
                    )
                )
            ).scalars()
            return [_to_slot(s) for s in rows]

    async def get_shift(self, shift_id: str) -> ShiftSlot | None:
        from app.db.models import Shift

        async with self._session_factory() as session:
            row = (
                await session.execute(select(Shift).where(Shift.id == shift_id))
            ).scalar_one_or_none()
            return _to_slot(row) if row else None

    async def mark_absent(self, shift_id: str) -> None:
        from app.db.models import Shift

        async with self._session_factory() as session:
            row = (await session.execute(select(Shift).where(Shift.id == shift_id))).scalar_one()
            row.status = "absent"
            await session.commit()

    async def assign_shift(self, shift_id: str, employee_id: str) -> None:
        from app.db.models import Shift

        if self._pending_assign_failures > 0:
            self._pending_assign_failures -= 1
            raise HrisError("simulated HRIS outage")
        async with self._session_factory() as session:
            row = (await session.execute(select(Shift).where(Shift.id == shift_id))).scalar_one()
            row.employee_id = employee_id
            row.status = "covered"
            await session.commit()

    async def unassign_shift(self, shift_id: str) -> None:
        from app.db.models import Shift

        async with self._session_factory() as session:
            row = (await session.execute(select(Shift).where(Shift.id == shift_id))).scalar_one()
            row.employee_id = None
            row.status = "open"
            await session.commit()

    async def list_availability_blocks(
        self, location_id: str, from_dt: datetime, to_dt: datetime
    ) -> list[AvailabilityBlock]:
        from app.db.models import AvailabilityBlock as BlockModel
        from app.db.models import Employee

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(BlockModel)
                    .join(Employee, Employee.id == BlockModel.employee_id)
                    .where(
                        Employee.location_id == location_id,
                        BlockModel.ends_at >= from_dt,
                        BlockModel.starts_at <= to_dt,
                    )
                )
            ).scalars()
            return [
                AvailabilityBlock(
                    employee_id=b.employee_id,
                    starts_at=b.starts_at,
                    ends_at=b.ends_at,
                    kind=b.kind,
                )
                for b in rows
            ]


def _to_slot(row: Any) -> ShiftSlot:
    return ShiftSlot(
        id=row.id,
        location_id=row.location_id,
        role=row.role,
        starts_at=_aware(row.starts_at),
        ends_at=_aware(row.ends_at),
        employee_id=row.employee_id,
        status=row.status,
    )


def _aware(moment: datetime) -> datetime:
    """SQLite drops tzinfo on storage; treat naive values as UTC."""
    if moment.tzinfo is None:

        return moment.replace(tzinfo=UTC)
    return moment
