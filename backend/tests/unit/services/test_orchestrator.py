"""Integration-style unit tests for the RescueOrchestrator core (spec §2, §7.4).

Runs against SQLite with the DB-backed mock workforce adapter, an in-memory
channel and scheduler, and a FakeClock.
"""

from datetime import timedelta

from sqlalchemy import func, select

from app.agent.interpreter import MessageInterpreter
from app.db.models import AuditEvent, Message, Offer, RescueCase, Shift
from app.db.seed import DEMO_LOCATION_ID

CONVERSATION = "conv_1"
PROVIDER_ID = "provider_msg_1"


class RefLLM:
    """Scripted LLM: classifies the report, then names shift_2 in the reply."""

    def __init__(self) -> None:
        self.calls = 0
        self.contexts: list[dict] = []
        self.last_usage = None

    async def interpret(self, message_body: str, context: dict) -> dict:
        self.calls += 1
        self.contexts.append(dict(context))
        if self.calls == 1:
            return {"intent": "ABSENCE_REPORT", "confidence": 0.95}
        return {
            "intent": "ABSENCE_REPORT",
            "confidence": 0.9,
            "shift_reference": "shift_2",
        }


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

    # The confirmation is persisted so the dashboard can show the conversation.
    async with db() as session:
        persisted = (
            await session.execute(
                select(Message).where(Message.template_key == "absence_confirm")
            )
        ).scalars().all()
    assert len(persisted) == 1
    # No manager notification and no offers before explicit confirmation.
    assert not [m for m in world.channel.sent if m["to"] == "+34600999001"]
    assert not [m for m in world.channel.sent if m["template_key"] == "offer"]


async def test_absence_audit_event_uses_the_real_case_id(world, db) -> None:
    """The dashboard timeline joins audit events on the case id.

    A synthetic `case_<shift>_<timestamp>` id used to be written here, which left
    every timeline query empty and split the audit trail across two namespaces.
    """
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="me encuentro fatal, hoy no puedo ir",
    )

    async with db() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        events = (await session.execute(select(AuditEvent))).scalars().all()

    reported = [e for e in events if e.type == "ABSENCE_REPORTED"]
    assert reported, "the absence report must be audited"
    assert all(e.rescue_id == case.id for e in reported)


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
        inbound = (
            await session.execute(
                select(func.count())
                .select_from(Message)
                .where(Message.direction == "inbound")
            )
        ).scalar_one()
    assert inbound == 1  # the duplicate provider message was ignored
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


async def test_shift_choice_reply_with_reference_opens_that_case(world, db, now) -> None:
    """LLM path: the reply names a candidate via shift_reference and the case
    opens for that shift — the question the agent asked has an answer path."""
    async with world.session_factory() as session:
        session.add(
            Shift(
                id="shift_2",
                location_id=DEMO_LOCATION_ID,
                role="bar",
                starts_at=now + timedelta(hours=4, minutes=20),
                ends_at=now + timedelta(hours=12, minutes=20),
                employee_id="emp_01_floor",
                status="scheduled",
            )
        )
        await session.commit()

    llm = RefLLM()
    world.orchestrator.interpreter = MessageInterpreter(llm=llm)

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="choice_1",
        text="hoy no puedo ir",
    )
    asks = [m for m in world.channel.sent if m["template_key"] == "ask_which_shift"]
    assert len(asks) == 1
    # The report call saw the shift list, not a pending choice.
    assert llm.contexts[0]["shifts_48h"]
    assert "pending_shift_choice" not in llm.contexts[0]

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="choice_2",
        text="el de las 19:00",
    )
    # Resolved without asking again.
    asks = [m for m in world.channel.sent if m["template_key"] == "ask_which_shift"]
    assert len(asks) == 1
    # The reply call carried the pending choice: same candidates as shifts_48h.
    assert llm.contexts[1]["pending_shift_choice"] == llm.contexts[1]["shifts_48h"]
    async with db() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
    assert case.shift_id == "shift_2"
    assert case.status == "OPEN"
    assert world.channel.with_template("absence_confirm")


async def test_degraded_mode_resolves_shift_choice_by_day(world, db, now) -> None:
    """Degraded mode: "mañana" deterministically picks the tomorrow shift."""
    async with world.session_factory() as session:
        session.add(
            Shift(
                id="shift_2",
                location_id=DEMO_LOCATION_ID,
                role="bar",
                starts_at=now + timedelta(days=1, hours=4),
                ends_at=now + timedelta(days=1, hours=12),
                employee_id="emp_01_floor",
                status="scheduled",
            )
        )
        await session.commit()

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="no puedo ir",
    )
    asks = [m for m in world.channel.sent if m["template_key"] == "ask_which_shift"]
    assert len(asks) == 1

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="provider_msg_2",
        text="no puedo ir mañana",
    )
    asks = [m for m in world.channel.sent if m["template_key"] == "ask_which_shift"]
    assert len(asks) == 1  # resolved without asking again
    async with db() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
    assert case.shift_id == "shift_2"
    assert case.status == "OPEN"


async def test_unresolvable_shift_choice_asks_once_more_then_redirects(world, db, now) -> None:
    """Never guess: one re-ask, then the polite redirect (spec §5.5)."""
    async with world.session_factory() as session:
        session.add(
            Shift(
                id="shift_2",
                location_id=DEMO_LOCATION_ID,
                role="bar",
                starts_at=now + timedelta(hours=4, minutes=20),
                ends_at=now + timedelta(hours=12, minutes=20),
                employee_id="emp_01_floor",
                status="scheduled",
            )
        )
        await session.commit()

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="no puedo ir",
    )
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="provider_msg_2",
        text="no puedo ir, en serio",
    )
    asks = [m for m in world.channel.sent if m["template_key"] == "ask_which_shift"]
    assert len(asks) == 2  # the question was re-sent exactly once

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="provider_msg_3",
        text="no puedo ir",
    )
    asks = [m for m in world.channel.sent if m["template_key"] == "ask_which_shift"]
    assert len(asks) == 2
    redirects = [m for m in world.channel.sent if m["template_key"] == "out_of_scope"]
    assert len(redirects) == 1
    async with db() as session:
        cases = (await session.execute(select(func.count()).select_from(RescueCase))).scalar_one()
    assert cases == 0  # never guessed between the two candidates


async def test_unconfirmed_absence_escalates_when_deadline_passes(world, db) -> None:
    """Ghost case: reported, never confirmed — the deadline escalates to the
    manager, and running the scheduler again never duplicates it (§5.5)."""
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="me encuentro fatal, hoy no puedo ir",
    )
    async with db() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
    assert case.status == "OPEN"

    world.clock.advance(timedelta(minutes=11))
    await world.scheduler.run_due(world.clock.now())

    async with db() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        escalations = (
            await session.execute(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.type == "ESCALATED")
            )
        ).scalar_one()
    assert case.status == "ESCALATED"
    assert world.channel.with_template("manager_escalated")
    assert escalations == 1

    await world.scheduler.run_due(world.clock.now())
    async with db() as session:
        escalations = (
            await session.execute(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.type == "ESCALATED")
            )
        ).scalar_one()
    assert escalations == 1


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


async def test_in_progress_shift_is_found_even_if_it_started_hours_ago(world, db, now) -> None:
    """spec §5.3: a shift already running can be covered for the remainder."""
    from sqlalchemy import select

    from app.db.models import Shift

    async with db() as session:
        shift = (await session.execute(select(Shift).where(Shift.id == "shift_1"))).scalar_one()
        shift.starts_at = now - timedelta(hours=6)
        shift.ends_at = now + timedelta(hours=2)
        await session.commit()

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id=PROVIDER_ID,
        text="me encuentro fatal, hoy no puedo ir",
    )

    assert world.channel.with_template("absence_confirm"), "in-progress shift not found"
    assert not world.channel.with_template("out_of_scope")


async def test_every_persisted_id_fits_the_database_column_width(world, db) -> None:
    """Postgres columns are VARCHAR(64): composed ids must never exceed it
    (a longer id rolled back the whole confirmation transaction once)."""
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

    # Drive the case to escalation too: the escalated audit id used to be
    # composed ("audit_<case>_escalated_<ts>_<event>") and reached 81 characters,
    # so the escalation transaction failed while this test stayed green because
    # it only ever exercised the confirmation path.
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="provider_msg_3",
        text="no puedo, lo siento",
    )
    world.clock.advance(timedelta(days=1))
    await world.scheduler.run_due(world.clock.now())

    from sqlalchemy import select

    from app.db.models import AuditEvent, Message, Offer, RescueCase

    async with db() as session:
        ids: list[str] = []
        ids += [row.id for row in (await session.execute(select(RescueCase))).scalars()]
        ids += [row.id for row in (await session.execute(select(Offer))).scalars()]
        ids += [row.id for row in (await session.execute(select(Message))).scalars()]
        ids += [row.id for row in (await session.execute(select(AuditEvent))).scalars()]

    assert ids, "expected persisted rows"
    assert any(
        row.type == "ESCALATED"
        for row in (await _audit_events(db))
    ), "the guard must cover the escalation path"
    too_long = [i for i in ids if len(i) > 64]
    assert too_long == [], f"ids exceeding VARCHAR(64): {too_long}"


async def _audit_events(db) -> list:
    from sqlalchemy import select

    from app.db.models import AuditEvent

    async with db() as session:
        return list((await session.execute(select(AuditEvent))).scalars())
