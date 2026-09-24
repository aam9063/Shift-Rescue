"""ShiftRescueTarget (spec §8.2): the full system exposed to the eval harness.

Mounts the stack with FakeClock, SimScheduler and SimulatedChannel, runs
entire scenarios in milliseconds, and snapshots the final world for the
deterministic invariant checker.
"""

import os
import tempfile
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.channels.simulated import SimulatedChannel
from app.core.clock import FakeClock
from app.db.models import (
    AuditEvent,
    Base,
    Employee,
    Location,
    Manager,
    Message,
    Offer,
    RescueCase,
    Shift,
)
from app.db.seed import DEMO_LOCATION_ID, DEMO_LOCATION_NAME, DEMO_MANAGER_EMAIL
from app.integrations.workforce.mock import MockWorkforceAdapter
from app.services.orchestrator import RescueOrchestrator
from app.workers.scheduler import SimScheduler


class ShiftRescueTarget:
    """Hermetic full-system harness: inject messages, advance the clock,
    snapshot the world."""

    def __init__(
        self,
        engine: Any,
        db: async_sessionmaker[AsyncSession],
        world_now: datetime,
        floor_count: int = 4,
    ) -> None:
        self._engine = engine
        self.session_factory = db
        self.clock = FakeClock(world_now)
        self.channel = SimulatedChannel()
        self.scheduler = SimScheduler()
        self.workforce = MockWorkforceAdapter(db)
        self.orchestrator = RescueOrchestrator(
            session_factory=db,
            workforce=self.workforce,
            channel=self.channel,
            scheduler=self.scheduler,
            clock=self.clock,
        )
        for name, handler in self.orchestrator.task_handlers().items():
            self.scheduler.register(name, handler)
        self.world_now = world_now
        self.employee_count = floor_count

    @classmethod
    async def create(
        cls,
        floor_count: int = 4,
        now: datetime | None = None,
        *,
        shift_starts_in: timedelta = timedelta(minutes=20),
        hris_fail_assignments: int = 0,
        llm_down: bool = False,
        timezone: str = "UTC",
    ) -> "ShiftRescueTarget":
        now = now or datetime(2026, 10, 3, 14, 40, tzinfo=UTC)
        # A temp FILE database avoids the StaticPool shared-connection quirks
        # of in-memory SQLite (nested session commits).
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        db = async_sessionmaker(engine, expire_on_commit=False)

        async with db() as session:
            session.add(Location(id=DEMO_LOCATION_ID, name=DEMO_LOCATION_NAME, timezone=timezone))
            session.add(
                Manager(
                    id="mgr_1",
                    name="Demo Manager",
                    email=DEMO_MANAGER_EMAIL,
                    phone_e164="+34600999001",
                    password_hash="x",
                    role="manager",
                    location_ids=[DEMO_LOCATION_ID],
                )
            )
            for i in range(1, floor_count + 1):
                session.add(
                    Employee(
                        id=f"emp_{i:02d}_floor",
                        location_id=DEMO_LOCATION_ID,
                        full_name=f"Floor {i}",
                        phone_e164=f"+3460000000{i}",
                        language="es",
                        roles=["floor"],
                        contract_weekly_hours=30,
                        max_weekly_hours=40,
                        home_zone="port",
                        accepts_extra_shifts=True,
                        active=True,
                    )
                )
            # Normalize to UTC: SQLite keeps the naive wall of whatever is stored.
            shift_start_utc = (now + shift_starts_in).astimezone(UTC)
            shift_end_utc = shift_start_utc + timedelta(hours=8)
            session.add(
                Shift(
                    id="shift_1",
                    location_id=DEMO_LOCATION_ID,
                    role="floor",
                    starts_at=shift_start_utc,
                    ends_at=shift_end_utc,
                    employee_id="emp_01_floor",
                    status="scheduled",
                )
            )
            await session.commit()

        target = cls(engine, db, now, floor_count)
        if hris_fail_assignments:
            target.workforce.fail_next_assignments(hris_fail_assignments)
        if llm_down:
            from app.agent.interpreter import MessageInterpreter

            class DownLLM:
                async def interpret(self, message_body: str, context: dict) -> dict:
                    raise TimeoutError("LLM provider down")

            target.orchestrator.interpreter = MessageInterpreter(
                llm=DownLLM(), confidence_threshold=0.75
            )
        return target

    async def inject_employee_message(
        self,
        employee_id: str,
        text: str,
        *,
        conversation_id: str | None = None,
        provider_message_id: str | None = None,
    ) -> None:
        """Inject an inbound message through the simulated channel path."""
        provider_message_id = provider_message_id or (
            f"prov_in_{employee_id}_{len(self.channel.sent)}"
        )
        await self.orchestrator.handle_inbound(
            conversation_id=conversation_id or f"conv_{employee_id}",
            employee_id=employee_id,
            provider_message_id=provider_message_id,
            text=text,
        )

    async def advance_clock(self, minutes: float) -> None:
        self.clock.advance(timedelta(minutes=minutes))
        await self.scheduler.run_due(self.clock.now())

    async def latest_pending_approval(self) -> str | None:
        from app.db.models import ApprovalRequest

        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(ApprovalRequest).where(ApprovalRequest.status == "pending")
                )
            ).scalars().first()
            return row.id if row else None

    async def snapshot(self) -> dict[str, Any]:
        async with self.session_factory() as session:
            case_row = (
                await session.execute(select(RescueCase))
            ).scalars().first()
            case = None
            if case_row is not None:
                case = {
                    "id": case_row.id,
                    "status": case_row.status,
                    "covering_employee_id": case_row.covering_employee_id,
                    "resolution": case_row.resolution,
                    "deadline_at": case_row.deadline_at,
                }
            offers = [
                {
                    "id": o.id,
                    "employee_id": o.employee_id,
                    "status": o.status,
                    "wave_number": o.wave_number,
                    "requires_approval": o.requires_approval,
                    "sent_at": o.sent_at,
                }
                for o in (await session.execute(select(Offer))).scalars()
            ]
            shift_row = (
                await session.execute(select(Shift).where(Shift.id == "shift_1"))
            ).scalar_one_or_none()
            shift = (
                {
                    "id": shift_row.id,
                    "status": shift_row.status,
                    "employee_id": shift_row.employee_id,
                    "starts_at": shift_row.starts_at,
                }
                if shift_row
                else None
            )
            audits = [
                {"type": a.type, "payload": dict(a.payload or {}), "id": a.id}
                for a in (await session.execute(select(AuditEvent))).scalars()
            ]
            messages = [
                {"id": m.id, "direction": m.direction, "body_redacted": m.body_redacted}
                for m in (await session.execute(select(Message))).scalars()
            ]
        return {
            "case": case,
            "offers": offers,
            "shift": shift,
            "audits": audits,
            "messages": messages,
            "channel_sent": list(self.channel.sent),
        }
