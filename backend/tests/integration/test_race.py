"""Integration tests on real PostgreSQL (spec §5.5, §7.4).

Requires DATABASE_URL pointing at a PostgreSQL instance (docker compose:
postgresql+asyncpg://shift_rescue:shift_rescue@localhost:5433/shift_rescue).
Skipped otherwise.
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.clock import FakeClock
from app.db.models import (
    AuditEvent,
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
from tests.unit.services.helpers import RecordingChannel

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires DATABASE_URL"),
]

NOW = datetime(2026, 10, 3, 14, 40, tzinfo=UTC)


class RecordingScheduler:
    def schedule(self, run_at, task_name, payload):
        return f"job_{run_at}_{task_name}"


def build_session_factory(url: str):
    return async_sessionmaker_from(url)


def async_sessionmaker_from(url: str):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False), engine


@pytest.fixture()
async def pg_world():
    url = os.environ["DATABASE_URL"]
    session_factory, engine = async_sessionmaker_from(url)

    # Clean slate for the demo tables (order matters for FK-less but sane state).
    async with session_factory() as session:
        for model in (
            AuditEvent,
            Message,
            Offer,
            RescueCase,
            Shift,
            Employee,
            Manager,
            Location,
        ):
            await session.execute(model.__table__.delete())
        session.add(Location(id=DEMO_LOCATION_ID, name=DEMO_LOCATION_NAME, timezone="UTC"))
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
                starts_at=NOW + timedelta(minutes=20),
                ends_at=NOW + timedelta(hours=8, minutes=20),
                employee_id="emp_01_floor",
                status="scheduled",
            )
        )
        await session.commit()

    world = _World(session_factory)
    yield world
    await engine.dispose()


class _World:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.workforce = MockWorkforceAdapter(session_factory)
        self.clock = FakeClock(NOW)
        self.channel = RecordingChannel()
        self.scheduler = RecordingScheduler()


def make_orchestrator(world: "_World") -> RescueOrchestrator:
    return RescueOrchestrator(
        session_factory=world.session_factory,
        workforce=world.workforce,
        channel=world.channel,
        scheduler=world.scheduler,
        clock=world.clock,
    )


async def test_acceptance_race_has_single_winner(pg_world) -> None:
    o1 = make_orchestrator(pg_world)
    await o1.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="provider_msg_1",
        text="me encuentro fatal, hoy no puedo ir",
    )
    await o1.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="provider_msg_2",
        text="sí",
    )

    async with pg_world.session_factory() as session:
        offers = sorted(
            (await session.execute(select(Offer))).scalars(), key=lambda o: o.employee_id
        )
        assert len(offers) == 3

    # Two candidates accept in the same instant, through independent
    # orchestrators (separate transactions on real PostgreSQL).
    o2 = make_orchestrator(pg_world)
    o3 = make_orchestrator(pg_world)
    await asyncio.gather(
        o2.handle_inbound(
            conversation_id="conv_emp_02_floor",
            employee_id="emp_02_floor",
            provider_message_id="accept_2",
            text="sí",
        ),
        o3.handle_inbound(
            conversation_id="conv_emp_03_floor",
            employee_id="emp_03_floor",
            provider_message_id="accept_3",
            text="sí",
        ),
    )

    async with pg_world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "COVERED"
        assert case.covering_employee_id in {"emp_02_floor", "emp_03_floor"}

        offers = (await session.execute(select(Offer))).scalars().all()
        accepted = [o for o in offers if o.status == "ACCEPTED"]
        assert len(accepted) == 1
        assert accepted[0].employee_id == case.covering_employee_id
        cancelled = [o for o in offers if o.status == "CANCELLED"]
        assert len(cancelled) == 2

        # The loser was told the shift was already covered (§5.5).
        already_covered = pg_world.channel.with_template("offer_already_covered")
        assert len(already_covered) >= 1

        shift = (await session.execute(select(Shift).where(Shift.id == "shift_1"))).scalar_one()
        assert shift.employee_id == case.covering_employee_id
        assert shift.status == "covered"

        count = (
            await session.execute(select(func.count()).select_from(RescueCase))
        ).scalar_one()
        assert count == 1


async def test_duplicate_provider_message_id_is_idempotent_on_postgres(pg_world) -> None:
    o = make_orchestrator(pg_world)
    await o.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="dup_msg",
        text="me encuentro fatal, hoy no puedo ir",
    )
    await o.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="dup_msg",
        text="me encuentro fatal, hoy no puedo ir",
    )

    async with pg_world.session_factory() as session:
        count = (await session.execute(select(func.count()).select_from(Message))).scalar_one()
        assert count == 1
        cases = (await session.execute(select(func.count()).select_from(RescueCase))).scalar_one()
        assert cases == 1  # OPEN case created once
