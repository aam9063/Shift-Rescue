"""Unit tests for the minimal demo seed (full seed arrives with domain-rules)."""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base
from app.db.seed import seed_database


async def test_seed_creates_demo_location_and_manager() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        await seed_database(session)

        from sqlalchemy import select

        from app.db.models import Location, Manager

        locations = (await session.execute(select(Location))).scalars().all()
        managers = (await session.execute(select(Manager))).scalars().all()

        assert len(locations) == 1
        assert locations[0].name == "La Terraza del Puerto"
        assert locations[0].timezone == "Europe/Madrid"
        assert len(managers) == 1
        assert managers[0].email == "manager@laterraza.demo"
        assert managers[0].role == "manager"


async def test_seed_is_idempotent() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        await seed_database(session)
        await seed_database(session)

        from sqlalchemy import func, select

        from app.db.models import Location

        count = (await session.execute(select(func.count()).select_from(Location))).scalar_one()
        assert count == 1
