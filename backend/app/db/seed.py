"""Minimal demo seed: La Terraza del Puerto + demo manager.

The full 25-employee, two-week schedule seed per spec §11 arrives with the
`domain-rules` feature. Idempotent by natural keys (location name, email).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Location, Manager

DEMO_LOCATION_NAME = "La Terraza del Puerto"
DEMO_MANAGER_EMAIL = "manager@laterraza.demo"
# Demo credential, documented in the README; replaced by seeded Argon2 hashes
# once auth lands. Never a real password.
DEMO_MANAGER_PASSWORD_HASH = "demo-not-a-real-hash"


async def seed_database(session: AsyncSession) -> None:
    location = (
        await session.execute(select(Location).where(Location.name == DEMO_LOCATION_NAME))
    ).scalar_one_or_none()
    if location is None:
        session.add(
            Location(name=DEMO_LOCATION_NAME, timezone="Europe/Madrid", address_zone="port")
        )

    manager = (
        await session.execute(select(Manager).where(Manager.email == DEMO_MANAGER_EMAIL))
    ).scalar_one_or_none()
    if manager is None:
        session.add(
            Manager(
                name="Demo Manager",
                email=DEMO_MANAGER_EMAIL,
                password_hash=DEMO_MANAGER_PASSWORD_HASH,
                role="manager",
            )
        )

    await session.commit()
