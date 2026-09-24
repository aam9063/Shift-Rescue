"""Quiet-hours gating in the orchestrator (spec §5.3)."""

from datetime import timedelta

from sqlalchemy import select

from app.db.models import AuditEvent, Offer
from tests.unit.services.helpers import build_world


async def test_offers_are_queued_during_quiet_hours_and_sent_after() -> None:
    # Shift starts 10h later (outside the 3h grace); clock set to 23:30.
    world, _ = await build_world(floor_count=4, shift_starts_in=timedelta(hours=18, minutes=20))
    await world.orchestrator.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="provider_msg_1",
        text="me encuentro fatal, hoy no puedo ir",
    )
    world.clock.set(world.now + timedelta(hours=8, minutes=50))  # 23:30, shift in 5h20m
    await world.orchestrator.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="provider_msg_2",
        text="sí",
    )

    # No offers sent while quiet hours are in force.
    assert not world.channel.with_template("offer")
    queued = [
        e for e in (await _audits(world)) if e.type == "OFFERS_QUEUED"
    ]
    assert queued
    # The wave send was deferred to 07:00.
    assert world.scheduler.pending_count() >= 1

    # Quiet hours end: the deferred send fires.
    world.clock.set(world.now + timedelta(hours=16, minutes=20))  # 07:00 next day
    await world.scheduler.run_due(world.clock.now())

    offers = (await _offers(world)).scalars().all()
    assert len(offers) == 3
    assert len(world.channel.with_template("offer")) == 3


async def _audits(world):


    async with world.session_factory() as session:
        return (await session.execute(select(AuditEvent))).scalars().all()


async def _offers(world):


    async with world.session_factory() as session:
        return await session.execute(select(Offer))
