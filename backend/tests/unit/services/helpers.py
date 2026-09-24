"""Shared test helpers for orchestrator tests."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.channels.simulated import SimulatedChannel
from app.core.clock import FakeClock
from app.db.models import Base, Employee, Location, Manager, Shift
from app.db.seed import DEMO_LOCATION_ID, DEMO_LOCATION_NAME, DEMO_MANAGER_EMAIL
from app.integrations.workforce.mock import MockWorkforceAdapter
from app.services.orchestrator import RescueOrchestrator
from app.workers.scheduler import SimScheduler

CONVERSATION = "conv_1"
PROVIDER_ID = "provider_msg_1"
MANAGER_PHONE = "+34600999001"


class World:
    def __init__(self, db: async_sessionmaker, now: datetime, floor_count: int = 4) -> None:
        self.session_factory = db
        self.workforce = MockWorkforceAdapter(db)
        self.clock = FakeClock(now)
        self.channel = SimulatedChannel()
        self.scheduler = SimScheduler()
        self.orchestrator = RescueOrchestrator(
            session_factory=db,
            workforce=self.workforce,
            channel=self.channel,
            scheduler=self.scheduler,
            clock=self.clock,
        )
        for name, handler in self.orchestrator.task_handlers().items():
            self.scheduler.register(name, handler)
        self.now = now
        self.floor_count = floor_count

    def to_manager(self) -> list[dict[str, Any]]:
        return self.channel.to(MANAGER_PHONE)


async def build_world(
    floor_count: int = 4,
    timezone: str = "UTC",
    shift_starts_in: timedelta = timedelta(minutes=20),
) -> tuple[World, Any]:
    """Fresh SQLite world: location, manager, N floor employees, one shift."""
    now = datetime(2026, 10, 3, 14, 40, tzinfo=UTC)
    import os
    import tempfile

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
                phone_e164=MANAGER_PHONE,
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
        session.add(
            Shift(
                id="shift_1",
                location_id=DEMO_LOCATION_ID,
                role="floor",
                starts_at=now + shift_starts_in,
                ends_at=now + shift_starts_in + timedelta(hours=8),
                employee_id="emp_01_floor",
                status="scheduled",
            )
        )
        await session.commit()

    world = World(db, now, floor_count)
    return world, engine


async def run_to_offering(world: World) -> list:
    """Drive report + confirmation; return pending offers sorted by employee."""
    from sqlalchemy import select

    from app.db.models import Offer

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="me encuentro fatal, hoy no puedo ir",
    )
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="provider_msg_2",
        text="sí",
    )
    async with world.session_factory() as session:
        offers = (await session.execute(select(Offer))).scalars().all()
        return sorted(offers, key=lambda o: o.employee_id)
