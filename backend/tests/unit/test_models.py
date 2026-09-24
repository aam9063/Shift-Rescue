"""Model tests: all spec §4.1 entities exist and behave on a real DB."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import (
    Base,
    Conversation,
    Employee,
    Location,
    Message,
    Offer,
    RescueCase,
    Shift,
)

EXPECTED_TABLES = {
    # workforce_mock
    "location",
    "employee",
    "shift",
    "availability_block",
    # rescue
    "rescue_case",
    "offer",
    "conversation",
    "message",
    "interpretation",
    "approval_request",
    "audit_event",
    "manager",
    "eval_run",
    "location_settings",
}


def test_all_spec_entities_are_modeled() -> None:
    assert set(Base.metadata.tables.keys()) >= EXPECTED_TABLES


async def test_employee_shift_rescue_offer_roundtrip() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        location = Location(name="La Terraza del Puerto", timezone="Europe/Madrid")
        session.add(location)
        await session.flush()  # assigns the PK before children reference it
        employee = _employee(location.id)
        shift = _shift(location.id, employee.id)
        rescue = _rescue_case(location.id, shift.id, employee.id)
        offer = _offer(rescue.id, employee.id)
        session.add_all([location, employee, shift, rescue, offer])
        await session.commit()

        loaded_shift = (
            await session.execute(select(Shift).where(Shift.id == shift.id))
        ).scalar_one()
        assert loaded_shift.status == "absent"
        loaded_offer = (
            await session.execute(select(Offer).where(Offer.id == offer.id))
        ).scalar_one()
        assert loaded_offer.status == "PENDING"


async def test_provider_message_id_is_unique() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        conversation = Conversation(id=str(uuid4()), channel="whatsapp")
        session.add_all(
            [
                _message(conversation.id, provider_message_id="dup-1"),
                _message(conversation.id, provider_message_id="dup-1"),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()


# --- helpers -----------------------------------------------------------------


def _employee(location_id: str) -> Employee:
    return Employee(
        id=str(uuid4()),
        location_id=location_id,
        full_name="Marta Lopez",
        phone_e164="+34600000001",
        language="es",
        roles=["floor"],
        contract_weekly_hours=30,
        max_weekly_hours=40,
        home_zone="port",
        accepts_extra_shifts=True,
        active=True,
    )


def _shift(location_id: str, employee_id: str) -> Shift:
    return Shift(
        id=str(uuid4()),
        location_id=location_id,
        role="floor",
        starts_at=datetime(2026, 10, 3, 15, 0, tzinfo=UTC),
        ends_at=datetime(2026, 10, 3, 23, 0, tzinfo=UTC),
        employee_id=employee_id,
        status="absent",
    )


def _rescue_case(location_id: str, shift_id: str, absent_employee_id: str) -> RescueCase:
    return RescueCase(
        id=str(uuid4()),
        location_id=location_id,
        shift_id=shift_id,
        absent_employee_id=absent_employee_id,
        origin="employee_message",
        status="OFFERING",
        opened_at=datetime(2026, 10, 3, 14, 40, tzinfo=UTC),
        deadline_at=datetime(2026, 10, 3, 14, 50, tzinfo=UTC),
    )


def _offer(rescue_id: str, employee_id: str) -> Offer:
    return Offer(
        id=str(uuid4()),
        rescue_id=rescue_id,
        employee_id=employee_id,
        wave_number=1,
        status="PENDING",
        sent_at=datetime(2026, 10, 3, 14, 41, tzinfo=UTC),
        expires_at=datetime(2026, 10, 3, 14, 51, tzinfo=UTC),
    )


def _message(conversation_id: str, provider_message_id: str) -> Message:
    return Message(
        id=str(uuid4()),
        conversation_id=conversation_id,
        direction="inbound",
        provider_message_id=provider_message_id,
        body_redacted="ok",
    )
