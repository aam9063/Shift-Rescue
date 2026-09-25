"""Tests for the full deterministic demo seed (spec §11)."""

from collections import Counter
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models import Base, Employee, Location, Manager, Shift
from app.db.seed import (
    DEMO_LOCATION_NAME,
    DEMO_REAL_PHONES_LIMIT,
    apply_real_phone_mapping,
    seed_database,
)


@pytest.fixture()
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def test_seed_creates_location_employees_and_managers(session_factory) -> None:
    async with session_factory() as session:
        await seed_database(session)

        assert (await session.execute(select(func.count()).select_from(Location))).scalar_one() == 1
        location = (await session.execute(select(Location))).scalar_one()
        assert location.name == DEMO_LOCATION_NAME
        assert location.timezone == "Europe/Madrid"

        employees = (await session.execute(select(Employee))).scalars().all()
        # Spec §11 says "unos 25": 27 with cleaning staff included.
        assert len(employees) == 27

        roles = Counter(role for e in employees for role in e.roles)
        assert roles["kitchen"] == 8
        assert roles["floor"] == 9
        assert roles["bar"] == 4
        assert roles["cleaning"] == 2
        assert roles["office"] == 2
        assert roles["supervisor"] == 2

        contracts = Counter(e.contract_weekly_hours for e in employees)
        assert set(contracts) == {20, 30, 40}

        assert len({e.home_zone for e in employees}) >= 3
        assert {e.accepts_extra_shifts for e in employees} == {True, False}

        managers = (await session.execute(select(Manager))).scalars().all()
        assert len(managers) == 2


async def test_seed_creates_two_weeks_of_shifts(session_factory) -> None:
    async with session_factory() as session:
        await seed_database(session)

        shifts = (await session.execute(select(Shift))).scalars().all()
        # 14 days, several shifts per role per day.
        assert len(shifts) >= 14 * 6
        days = {s.starts_at.date() for s in shifts}
        assert len(days) == 14
        # Every shift is assigned: the seed schedules a fully staffed fortnight.
        assert all(s.employee_id is not None for s in shifts)
        # All shifts belong to the demo location.
        location = (await session.execute(select(Location))).scalar_one()
        assert all(s.location_id == location.id for s in shifts)


async def test_seed_exercises_edge_cases(session_factory) -> None:
    async with session_factory() as session:
        await seed_database(session)

        # Someone closes (ends late) and someone has high weekly load: the
        # schedule must include late-ending shifts and a near-cap employee.
        shifts = (await session.execute(select(Shift))).scalars().all()
        assert any(s.ends_at.hour >= 23 for s in shifts)
        weekly = Counter(s.employee_id for s in shifts)
        assert weekly.most_common(1)[0][1] >= 8  # at least one heavily loaded employee


async def test_seed_is_deterministic_and_idempotent(session_factory) -> None:
    async with session_factory() as session:
        await seed_database(session)
        employees_first = sorted(e.id for e in (await session.execute(select(Employee))).scalars())
        shifts_first = sorted(s.id for s in (await session.execute(select(Shift))).scalars())
        await seed_database(session)
        employees_second = sorted(e.id for e in (await session.execute(select(Employee))).scalars())
        shifts_second = sorted(s.id for s in (await session.execute(select(Shift))).scalars())

    assert employees_first == employees_second
    assert shifts_first == shifts_second

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(Employee))
        assert count == 27


async def test_seed_is_reproducible_across_databases() -> None:
    snapshots = []
    for _ in range(2):
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await seed_database(session)
            employees = sorted(e.id for e in (await session.execute(select(Employee))).scalars())
            shifts = sorted(
                (s.id, s.employee_id) for s in (await session.execute(select(Shift))).scalars()
            )
            snapshots.append((employees, shifts))
        await engine.dispose()
    assert snapshots[0] == snapshots[1]


async def test_real_phone_mapping_applies_at_most_three(session_factory) -> None:
    async with session_factory() as session:
        await seed_database(session)
        employees = (await session.execute(select(Employee))).scalars().all()

        settings = Settings(
            _env_file=None,
            demo_real_phones="emp_01_kitchen=+34600111222|Bruno T.:not-a-phone",
        )
        apply_real_phone_mapping(employees, settings)

        mapped = [e for e in employees if e.phone_e164.startswith("+3460011")]
        assert len(mapped) == 1
        assert mapped[0].id == "emp_01_kitchen"
        assert DEMO_REAL_PHONES_LIMIT == 3


async def test_seed_clears_previous_shifts_before_reinserting(session_factory) -> None:
    async with session_factory() as session:
        await seed_database(session)
        location = (await session.execute(select(Location))).scalar_one()
        # Simulate stale data from a previous run with different content.
        await session.execute(delete(Shift).where(Shift.location_id == location.id))
        stale = Shift(
            id="stale_1",
            location_id=location.id,
            role="floor",
            starts_at=datetime(2026, 9, 1, tzinfo=UTC),
            ends_at=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
            employee_id=None,
            status="open",
        )
        session.add(stale)
        await session.commit()

        await seed_database(session)
        shifts = (await session.execute(select(Shift))).scalars().all()
        assert all(s.id != "stale_1" for s in shifts)
