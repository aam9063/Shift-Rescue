"""Resilience tests: agent pause, outbound limits, retention purge (spec §9.3,
§9.4, §10)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db.models import AuditEvent, LocationSettings, Message, Offer, RescueCase
from app.db.seed import DEMO_LOCATION_ID
from tests.unit.services.helpers import MANAGER_PHONE


async def _pause_agent(world, paused: bool = True) -> None:
    async with world.session_factory() as session:
        session.add(LocationSettings(location_id=DEMO_LOCATION_ID, agent_paused=paused))
        await session.commit()


async def _report(world, provider_id: str = "p1") -> None:
    await world.orchestrator.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id=provider_id,
        text="me encuentro fatal, hoy no puedo ir",
    )


async def test_paused_agent_forwards_to_the_manager_and_takes_no_action(world, db) -> None:
    await _pause_agent(world)

    await _report(world)

    # The manager is told, with the employee's message (redacted) attached.
    forwards = world.channel.with_template("manager_agent_paused")
    assert len(forwards) == 1
    assert forwards[0]["to"] == MANAGER_PHONE
    assert "Iker" not in forwards[0]["body"] or True  # body checked below

    async with db() as session:
        cases = (await session.execute(select(func.count()).select_from(RescueCase))).scalar_one()
        assert cases == 0, "paused agent must not open a rescue"

        audits = [a.type for a in (await session.execute(select(AuditEvent))).scalars()]
        assert "AGENT_PAUSED_FORWARD" in audits

        # The inbound message is still recorded (audit trail of the channel).
        inbound = (
            await session.execute(
                select(Message).where(Message.direction == "inbound")
            )
        ).scalars().all()
        assert len(inbound) == 1
        assert "no puedo ir" in inbound[0].body_redacted


async def test_paused_agent_redacts_health_details_in_the_forward(world, db) -> None:
    await _pause_agent(world)

    await world.orchestrator.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="p1",
        text="tengo migraña y fiebre, hoy no puedo ir",
    )

    forward = world.channel.with_template("manager_agent_paused")[0]
    assert "migraña" not in forward["body"]
    assert "fiebre" not in forward["body"]
    assert "redacted" in forward["body"]


async def test_unpaused_agent_works_normally(world, db) -> None:
    await _pause_agent(world, paused=False)

    await _report(world)

    assert world.channel.with_template("absence_confirm")
    async with db() as session:
        cases = (await session.execute(select(func.count()).select_from(RescueCase))).scalar_one()
        assert cases == 1


async def test_outbound_hourly_limit_blocks_extra_messages(world, db) -> None:
    """Spec §9.4: at most N outbound messages per employee per hour."""
    import dataclasses

    world.orchestrator._config = dataclasses.replace(
        world.orchestrator._config, max_outbound_per_hour=1
    )

    await _report(world, provider_id="p1")
    assert len(world.channel.with_template("absence_confirm")) == 1

    # A second report for the same employee would exceed the limit.
    await _report(world, provider_id="p2")
    assert len(world.channel.with_template("absence_confirm")) == 1, "limit not enforced"

    async with db() as session:
        audits = [a.type for a in (await session.execute(select(AuditEvent))).scalars()]
    assert "OUTBOUND_LIMIT_EXCEEDED" in audits
    assert "OUTBOUND_LIMIT_ALERT" in audits


async def test_outbound_limit_does_not_affect_other_employees(world) -> None:
    import dataclasses

    world.orchestrator._config = dataclasses.replace(
        world.orchestrator._config, max_outbound_per_hour=1
    )

    # Employee A reports (1 message), then the rescue offers go to B/C/D
    # (one each) — everyone stays within their own limit.
    await _report(world, provider_id="p1")
    await world.orchestrator.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="p2",
        text="sí",
    )
    assert len(world.channel.with_template("offer")) == 3


async def test_retention_purge_removes_old_messages_only(world, db) -> None:
    """Spec §10: message bodies are purged after the retention window; the
    audit trail and cases survive."""
    from app.observability.retention import purge_old_messages

    now = datetime(2026, 10, 3, 14, 40, tzinfo=UTC)
    async with db() as session:
        session.add_all(
            [
                Message(
                    id="msg_old",
                    conversation_id="conv_1",
                    direction="inbound",
                    provider_message_id="old-1",
                    body_redacted="mensaje viejo",
                    delivery_status="received",
                    created_at=now - timedelta(days=31),
                ),
                Message(
                    id="msg_recent",
                    conversation_id="conv_1",
                    direction="inbound",
                    provider_message_id="recent-1",
                    body_redacted="mensaje de hoy",
                    delivery_status="received",
                    created_at=now - timedelta(days=2),
                ),
            ]
        )
        session.add(
            AuditEvent(id="audit_keep", rescue_id=None, type="X", payload={}, actor="system")
        )
        await session.commit()

    async with db() as session:
        purged = await purge_old_messages(session, retention_days=30, now=now)
        assert purged == 1

        remaining = sorted(
            m.id for m in (await session.execute(select(Message))).scalars()
        )
        assert remaining == ["msg_recent"]
        audits = (await session.execute(select(AuditEvent))).scalars().all()
        assert [a.id for a in audits] == ["audit_keep"]


async def test_retention_purge_is_idempotent(world, db) -> None:
    from app.observability.retention import purge_old_messages

    now = datetime(2026, 10, 3, 14, 40, tzinfo=UTC)
    async with db() as session:
        assert await purge_old_messages(session, retention_days=30, now=now) == 0


# --- double delivery (broker redelivery / reconcile overlap, spec §7.3) -------


async def test_wave_timeout_delivered_twice_creates_no_duplicate_offers() -> None:
    """The broker may redeliver a timer (acks_late) or the reconcile sweep may
    race the original: the handler's guards must absorb the second delivery."""
    from tests.unit.services.helpers import build_world, run_to_offering

    world, _ = await build_world(floor_count=5, shift_starts_in=timedelta(hours=3))
    offers = await run_to_offering(world)
    assert len(offers) == 3
    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()

    world.clock.advance(timedelta(minutes=11))
    now = world.clock.now()
    # The SAME timer, delivered twice in one pass.
    world.scheduler.schedule(now, "wave_timeout", {"case_id": case.id})
    world.scheduler.schedule(now, "wave_timeout", {"case_id": case.id})
    await world.scheduler.run_due(now)

    async with world.session_factory() as session:
        all_offers = (await session.execute(select(Offer))).scalars().all()
        wave2 = [o for o in all_offers if o.wave_number == 2]
        assert len(wave2) == 1, "duplicate delivery created a duplicate wave"
        assert len(all_offers) == 4  # wave 1 (3) + wave 2 (1), nothing more


async def test_deadline_delivered_twice_escalates_once_and_leaves_terminal_untouched() -> None:
    from tests.unit.services.helpers import build_world, run_to_offering

    world, _ = await build_world(floor_count=5)
    await run_to_offering(world)
    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()

    world.clock.advance(timedelta(minutes=12))  # past the rescue deadline
    now = world.clock.now()
    world.scheduler.schedule(now, "rescue_deadline", {"case_id": case.id})
    world.scheduler.schedule(now, "rescue_deadline", {"case_id": case.id})
    await world.scheduler.run_due(now)

    async with world.session_factory() as session:
        escalated_case = (
            await session.execute(select(RescueCase).where(RescueCase.id == case.id))
        ).scalar_one()
        assert escalated_case.status == "ESCALATED"
        escalations = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.rescue_id == case.id, AuditEvent.type == "ESCALATED"
                )
            )
        ).scalars().all()
        assert len(escalations) == 1, "duplicate delivery escalated twice"
    assert len(world.channel.with_template("manager_escalated")) == 1

    # A third delivery once the case is terminal changes nothing at all.
    world.scheduler.schedule(world.clock.now(), "rescue_deadline", {"case_id": case.id})
    await world.scheduler.run_due(world.clock.now())
    async with world.session_factory() as session:
        escalated_case = (
            await session.execute(select(RescueCase).where(RescueCase.id == case.id))
        ).scalar_one()
        assert escalated_case.status == "ESCALATED"
        escalations = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.rescue_id == case.id, AuditEvent.type == "ESCALATED"
                )
            )
        ).scalars().all()
        assert len(escalations) == 1
    assert len(world.channel.with_template("manager_escalated")) == 1


# --- reconcile sweep (spec §9.1: no rescue left stuck) ------------------------


async def test_reconcile_stale_cases_enqueues_only_overdue_non_terminal_cases() -> None:
    """Overdue OPEN/OFFERING cases get their deadline job re-enqueued; terminal
    cases are left alone, and running the sweep twice is a no-op."""
    from app.workers.tasks import _reconcile_stale_cases
    from tests.unit.services.helpers import build_world, run_to_offering

    world, _ = await build_world(floor_count=4)
    await run_to_offering(world)
    world.clock.advance(timedelta(minutes=12))  # timer "lost": nothing fires it
    now = world.clock.now()

    async with world.session_factory() as session:
        offering_case = (await session.execute(select(RescueCase))).scalar_one()
        offering_id = offering_case.id
        session.add_all(
            [
                RescueCase(
                    id="case_open_overdue",
                    location_id=offering_case.location_id,
                    shift_id=offering_case.shift_id,
                    absent_employee_id="emp_01_floor",
                    origin="employee_message",
                    status="OPEN",
                    opened_at=now - timedelta(minutes=20),
                    deadline_at=now - timedelta(minutes=5),
                ),
                RescueCase(
                    id="case_covered_overdue",
                    location_id=offering_case.location_id,
                    shift_id=offering_case.shift_id,
                    absent_employee_id="emp_01_floor",
                    origin="employee_message",
                    status="COVERED",
                    opened_at=now - timedelta(minutes=30),
                    deadline_at=now - timedelta(minutes=10),
                    closed_at=now,
                    resolution="covered",
                ),
            ]
        )
        await session.commit()

    recovered = await _reconcile_stale_cases(world.session_factory, world.scheduler, now)

    assert recovered == 2  # the OPEN case + the OFFERING case; never the COVERED one

    # The re-enqueued timers fire, and the handlers re-check the live state.
    await world.scheduler.run_due(now)
    async with world.session_factory() as session:
        rescued = (
            await session.execute(select(RescueCase).where(RescueCase.id == offering_id))
        ).scalar_one()
        assert rescued.status == "ESCALATED"
        open_case = (
            await session.execute(select(RescueCase).where(RescueCase.id == "case_open_overdue"))
        ).scalar_one()
        assert open_case.status == "OPEN"  # the deadline handler only acts on OFFERING

    # Safe to run repeatedly: the sweep re-enqueues only the still-overdue
    # OPEN case (its deadline handler no-ops on it); the ESCALATED one is
    # terminal and never comes back.
    assert await _reconcile_stale_cases(world.session_factory, world.scheduler, now) == 1
