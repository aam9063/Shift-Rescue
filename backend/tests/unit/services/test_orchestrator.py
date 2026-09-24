"""Integration-style unit tests for the RescueOrchestrator core (spec §2, §7.4).

Runs against SQLite with the DB-backed mock workforce adapter, an in-memory
channel and scheduler, and a FakeClock.
"""

from datetime import timedelta

from sqlalchemy import func, select

from app.db.models import AuditEvent, Message, Offer, RescueCase, Shift
from app.db.seed import DEMO_LOCATION_ID

CONVERSATION = "conv_1"
PROVIDER_ID = "provider_msg_1"


async def test_absence_report_sends_confirmation_and_no_case_yet(world, db, now) -> None:
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="me encuentro fatal, hoy no puedo ir",
    )



    async with db() as session:
        cases = (await session.execute(select(RescueCase))).scalars().all()
        assert len(cases) == 1
        assert cases[0].status == "OPEN"  # detected, awaiting explicit confirmation
        assert cases[0].shift_id == "shift_1"

    confirms = [m for m in world.channel.sent if m["template_key"] == "absence_confirm"]
    assert len(confirms) == 1
    assert confirms[0]["to"] == "+34600000001"
    # No manager notification and no offers before explicit confirmation.
    assert not [m for m in world.channel.sent if m["to"] == "+34600999001"]
    assert not [m for m in world.channel.sent if m["template_key"] == "offer"]


async def test_confirmation_opens_case_offering_with_first_wave(world, db, now) -> None:
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


    from app.db.models import Shift

    async with db() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "OFFERING"
        assert case.absent_employee_id == "emp_01_floor"
        # SQLite drops tzinfo on storage.
        assert case.deadline_at == (now + timedelta(minutes=10)).replace(tzinfo=None)

        shift = (await session.execute(select(Shift).where(Shift.id == "shift_1"))).scalar_one()
        assert shift.status == "absent"

        offers = (await session.execute(select(Offer))).scalars().all()
        assert len(offers) == 3  # wave_size default
        assert all(o.wave_number == 1 and o.status == "PENDING" for o in offers)
        offered_ids = {o.employee_id for o in offers}
        assert "emp_01_floor" not in offered_ids

        events = (await session.execute(select(AuditEvent))).scalars().all()
        assert any(e.type == "RESCUE_OPENED" for e in events)
        assert any(e.type == "OFFER_SENT" for e in events)

    offer_msgs = [m for m in world.channel.sent if m["template_key"] == "offer"]
    assert len(offer_msgs) == 3
    manager_msgs = [m for m in world.channel.sent if m["to"] == "+34600999001"]
    assert manager_msgs  # manager notified


async def test_duplicate_provider_message_is_processed_once(world, db) -> None:
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="me encuentro fatal, hoy no puedo ir",
    )
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="me encuentro fatal, hoy no puedo ir",
    )



    async with db() as session:
        count = (await session.execute(select(func.count()).select_from(Message))).scalar_one()
    assert count == 1
    assert len([m for m in world.channel.sent if m["template_key"] == "absence_confirm"]) == 1


async def test_two_shifts_same_day_asks_which_one(world) -> None:

    async with world.session_factory() as session:
        session.add(
            Shift(
                id="shift_2",
                location_id=DEMO_LOCATION_ID,
                role="floor",
                starts_at=world.clock.now() + timedelta(hours=4, minutes=20),
                ends_at=world.clock.now() + timedelta(hours=12, minutes=20),
                employee_id="emp_01_floor",
                status="scheduled",
            )
        )
        await session.commit()

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="hoy no puedo ir",
    )

    asks = [m for m in world.channel.sent if m["template_key"] == "ask_which_shift"]
    assert len(asks) == 1
    assert "15:00" in asks[0]["body"] and "19:00" in asks[0]["body"]


async def test_confirm_without_pending_gets_polite_redirect(world) -> None:
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="sí",
    )

    redirects = [m for m in world.channel.sent if m["template_key"] == "out_of_scope"]
    assert len(redirects) == 1


    async with world.session_factory() as session:
        cases = (await session.execute(select(func.count()).select_from(RescueCase))).scalar_one()
    assert cases == 0


async def test_health_details_are_redacted_before_persisting(world, db) -> None:
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="me encuentro fatal, tengo migraña y fiebre, hoy no puedo ir",
    )



    async with db() as session:
        messages = (await session.execute(select(Message))).scalars().all()
    inbound = [m for m in messages if m.direction == "inbound"]
    assert inbound[0].body_redacted == "[redacted: health details]"
    assert "migraña" not in inbound[0].body_redacted
