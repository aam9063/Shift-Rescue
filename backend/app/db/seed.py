"""Deterministic demo seed (spec §11): La Terraza del Puerto.

Fixed IDs and a fixed schedule pattern make every run reproducible: the same
database state is produced on any machine, twice. The schedule deliberately
exercises the eligibility rules (closing-then-opening rest violations, split
floor shifts, weekend reinforcement, heavily loaded employees).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import (
    AvailabilityBlock,
    Employee,
    Location,
    LocationSettings,
    Manager,
    Shift,
)

DEMO_LOCATION_NAME = "La Terraza del Puerto"
DEMO_LOCATION_ID = "loc_la_terraza"
DEMO_MANAGER_EMAIL = "manager@laterraza.demo"
DEMO_OPERATOR_EMAIL = "operator@laterraza.demo"
DEMO_PASSWORD_HASH = "demo-not-a-real-hash"  # replaced by Argon2 hashes when auth lands
DEMO_REAL_PHONES_LIMIT = 3

SEED_START_DATE = datetime(2026, 9, 28)  # Monday
SEED_DAYS = 14

_ROLE_NAMES: dict[str, list[str]] = {
    "kitchen": [
        "Ana García",
        "Bruno Torres",
        "Carla Ruiz",
        "Diego Fontán",
        "Elena Prieto",
        "Fabio Serra",
        "Gloria Márquez",
        "Hugo Vidal",
    ],
    "floor": [
        "Iker Mendoza",
        "Julia Campos",
        "Kevin Duarte",
        "Lucía Fuentes",
        "Marta López",
        "Nerea Vidal",
        "Óscar Peña",
        "Pablo Sanz",
        "Rita Cardoso",
    ],
    "bar": ["Sonia Peral", "Tomás Ibarra", "Uxia Rivas", "Víctor Lago"],
    "cleaning": ["Wanda Gil", "Xoel Barreiro"],
    "office": ["Yolanda Rey", "Zacarías Lemos"],
    "supervisor": ["Javier Prado", "Ainhoa Tobal"],
}

_HOME_ZONES = ["port", "north", "old_town", "beach", "port", "beach", "north", "old_town"]
_CONTRACTS = [20, 30, 40]


def _employees() -> list[Employee]:
    employees: list[Employee] = []
    counter = 0
    for role, names in _ROLE_NAMES.items():
        for _index, full_name in enumerate(names):
            counter += 1
            employees.append(
                Employee(
                    id=f"emp_{counter:02d}_{role}",
                    location_id=DEMO_LOCATION_ID,
                    full_name=full_name,
                    phone_e164=f"+3460000{counter:05d}",
                    language="es" if counter % 4 else "en",
                    roles=[role],
                    contract_weekly_hours=_CONTRACTS[counter % len(_CONTRACTS)],
                    max_weekly_hours=40 if counter % 3 else 30,
                    home_zone=_HOME_ZONES[counter % len(_HOME_ZONES)],
                    accepts_extra_shifts=counter % 2 == 0,
                    active=True,
                )
            )
    return employees


def _shift(
    role: str,
    day_offset: int,
    slot: str,
    starts: datetime,
    ends: datetime,
    employee_id: str,
) -> Shift:
    date = (SEED_START_DATE + timedelta(days=day_offset)).date().isoformat()
    return Shift(
        id=f"shift_lt_{date}_{role}_{slot}",
        location_id=DEMO_LOCATION_ID,
        role=role,
        starts_at=starts,
        ends_at=ends,
        employee_id=employee_id,
        status="scheduled",
    )


def _shifts() -> list[Shift]:
    shifts: list[Shift] = []
    zone = SEED_START_DATE.replace(tzinfo=UTC)

    def at(day_offset: int, hour: int) -> datetime:
        return zone + timedelta(days=day_offset, hours=hour)

    for d in range(SEED_DAYS):
        weekend = (SEED_START_DATE + timedelta(days=d)).weekday() >= 5

        # Kitchen: morning 07-15, afternoon 15-23.
        shifts.append(
            _shift("kitchen", d, "am", at(d, 7), at(d, 15), f"emp_{d % 8 + 1:02d}_kitchen")
        )
        shifts.append(
            _shift(
                "kitchen", d, "pm", at(d, 15), at(d, 23), f"emp_{(d + 4) % 8 + 1:02d}_kitchen"
            )
        )

        # Floor: morning 07-15, split 13-21 (partido), evening 15-23.
        # The evening employee opens the next morning -> rest-rule exercise.
        shifts.append(
            _shift("floor", d, "am", at(d, 7), at(d, 15), f"emp_{(d + 1) % 9 + 9:02d}_floor")
        )
        shifts.append(
            _shift(
                "floor", d, "split", at(d, 13), at(d, 21), f"emp_{(d + 3) % 9 + 9:02d}_floor"
            )
        )
        shifts.append(
            _shift("floor", d, "pm", at(d, 15), at(d, 23), f"emp_{d % 9 + 9:02d}_floor")
        )
        if weekend:  # weekend reinforcement
            shifts.append(
                _shift(
                    "floor",
                    d,
                    "reinforcement",
                    at(d, 12),
                    at(d, 16),
                    f"emp_{(d + 5) % 9 + 9:02d}_floor",
                )
            )

        # Bar: open 10-18, close 18-01 (crosses midnight; closer opens next day).
        shifts.append(
            _shift("bar", d, "open", at(d, 10), at(d, 18), f"emp_{d % 4 + 18:02d}_bar")
        )
        shifts.append(
            _shift(
                "bar", d, "close", at(d, 18), at(d + 1, 1), f"emp_{(d + 1) % 4 + 18:02d}_bar"
            )
        )

        # Cleaning: early 06-10, evening 20-00.
        shifts.append(_shift("cleaning", d, "am", at(d, 6), at(d, 10), "emp_23_cleaning"))
        shifts.append(_shift("cleaning", d, "pm", at(d, 20), at(d + 1, 0), "emp_24_cleaning"))

        # Supervisors: 11-19, alternating.
        supervisor_id = f"emp_{d % 2 + 25:02d}_supervisor"
        shifts.append(_shift("supervisor", d, "main", at(d, 11), at(d, 19), supervisor_id))

    return shifts


def _availability_blocks() -> list[AvailabilityBlock]:
    """A few unavailable windows over the fortnight."""
    zone = SEED_START_DATE.replace(tzinfo=UTC)

    def at(day_offset: int, hour: int) -> datetime:
        return zone + timedelta(days=day_offset, hours=hour)

    return [
        AvailabilityBlock(
            id=f"block_lt_{i}",
            employee_id=employee_id,
            starts_at=at(start_day, start_hour),
            ends_at=at(end_day, end_hour),
            kind="unavailable",
        )
        for i, (employee_id, start_day, start_hour, end_day, end_hour) in enumerate(
            [
                ("emp_09_floor", 2, 12, 3, 8),
                ("emp_01_kitchen", 5, 7, 5, 15),
                ("emp_18_bar", 8, 18, 9, 2),
                ("emp_10_floor", 11, 7, 12, 15),
            ],
            start=1,
        )
    ]


def apply_real_phone_mapping(employees: list[Employee], settings: Settings) -> int:
    """Map up to DEMO_REAL_PHONES_LIMIT employees to real sandbox numbers.

    Entries are `employee_id=phone` or `full_name=phone`, separated by `|`.
    Employee id matching is preferred (ASCII-safe and stable).
    """
    if not settings.demo_real_phones:
        return 0
    by_id = {e.id: e for e in employees}
    by_name = {e.full_name: e for e in employees}
    applied = 0
    for pair in settings.demo_real_phones.split("|"):
        if applied >= DEMO_REAL_PHONES_LIMIT:
            break
        key, _, phone = pair.partition("=")
        key = key.strip()
        phone = phone.strip()
        employee = by_id.get(key) or by_name.get(key)
        if employee is None or not phone.startswith("+") or not phone[1:].isdigit():
            continue
        employee.phone_e164 = phone
        applied += 1
    return applied


async def seed_database(session: AsyncSession) -> None:
    settings = get_settings()

    location = (
        await session.execute(select(Location).where(Location.name == DEMO_LOCATION_NAME))
    ).scalar_one_or_none()
    if location is None:
        location = Location(id=DEMO_LOCATION_ID, name=DEMO_LOCATION_NAME, timezone="Europe/Madrid")
        session.add(location)
    location.timezone = "Europe/Madrid"

    # Replace the demo snapshot for this location (deterministic + idempotent).
    await session.execute(delete(Shift).where(Shift.location_id == DEMO_LOCATION_ID))
    employee_ids = [e.id for e in _employees()]
    await session.execute(
        delete(AvailabilityBlock).where(AvailabilityBlock.employee_id.in_(employee_ids))
    )
    await session.execute(delete(Employee).where(Employee.location_id == DEMO_LOCATION_ID))
    await session.execute(
        delete(LocationSettings).where(LocationSettings.location_id == DEMO_LOCATION_ID)
    )

    employees = _employees()
    apply_real_phone_mapping(employees, settings)
    session.add_all(employees)
    session.add_all(_shifts())
    session.add_all(_availability_blocks())
    session.add(
        LocationSettings(
            location_id=DEMO_LOCATION_ID,
            ranking_weights={
                "equity": 0.4,
                "proximity": 0.3,
                "preference": 0.2,
                "no_overtime": 0.1,
            },
        )
    )

    for email, name, role in (
        (DEMO_MANAGER_EMAIL, "Demo Manager", "manager"),
        (DEMO_OPERATOR_EMAIL, "Demo Operator", "operator"),
    ):
        manager = (
            await session.execute(select(Manager).where(Manager.email == email))
        ).scalar_one_or_none()
        if manager is None:
            session.add(
                Manager(
                    name=name,
                    email=email,
                    password_hash=DEMO_PASSWORD_HASH,
                    role=role,
                )
            )

    await session.commit()
