"""Shared fixtures for orchestrator tests (SQLite + fakes + FakeClock)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base, Employee, Location, Manager, Shift
from app.db.seed import DEMO_LOCATION_ID, DEMO_LOCATION_NAME, DEMO_MANAGER_EMAIL
from tests.unit.services.helpers import MANAGER_PHONE, World

CONVERSATION = "conv_1"
PROVIDER_ID = "provider_msg_1"


@pytest.fixture()
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture()
def now() -> datetime:
    return datetime(2026, 10, 3, 14, 40, tzinfo=UTC)


@pytest.fixture()
async def world(db, now):
    """Minimal world: location, manager, 4 floor employees, one absent shift."""

    async with db() as session:
        session.add(Location(id=DEMO_LOCATION_ID, name=DEMO_LOCATION_NAME, timezone="UTC"))
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
        for i in range(1, 5):
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
                starts_at=now + timedelta(minutes=20),
                ends_at=now + timedelta(hours=8, minutes=20),
                employee_id="emp_01_floor",
                status="scheduled",
            )
        )
        await session.commit()

    return World(db, now, floor_count=4)
