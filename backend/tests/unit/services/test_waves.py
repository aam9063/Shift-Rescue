"""Wave, timeout and escalation tests via SimScheduler (spec §5.3)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models import Offer, RescueCase
from tests.unit.services.helpers import build_world, run_to_offering


async def test_wave_expiry_triggers_next_wave() -> None:
    # Shift starts in 3h: deadline (start - 30min) leaves room for two waves.
    world, _ = await build_world(floor_count=5, shift_starts_in=timedelta(hours=3))
    offers = await run_to_offering(world)
    assert len(offers) == 3  # wave 1

    # Advance past the first wave expiry and run due jobs.
    world.clock.advance(timedelta(minutes=11))
    await world.scheduler.run_due(world.clock.now())

    async with world.session_factory() as session:
        all_offers = (await session.execute(select(Offer))).scalars().all()
        wave2 = [o for o in all_offers if o.wave_number == 2]
        assert len(wave2) == 1  # only one candidate left
        # Spec 5.3: previous-wave offers stay alive until the rescue closes.
        wave1 = [o for o in all_offers if o.wave_number == 1]
        assert all(o.status == "PENDING" for o in wave1)

    offered = [m for m in world.channel.with_template("offer")]
    assert len(offered) == 4  # 3 + 1


async def test_candidates_exhausted_escalates_with_manager_notice() -> None:
    world, _ = await build_world(floor_count=4)  # 3 candidates, none left for wave 2
    await run_to_offering(world)

    world.clock.advance(timedelta(minutes=11))
    await world.scheduler.run_due(world.clock.now())

    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "ESCALATED"
    escalated = world.channel.with_template("manager_escalated")
    assert escalated


async def test_deadline_reached_escalates_even_between_waves() -> None:
    world, _ = await build_world(floor_count=5)
    await run_to_offering(world)

    # Jump straight past the rescue deadline (opened + 10 min).
    world.clock.advance(timedelta(minutes=12))
    await world.scheduler.run_due(world.clock.now())

    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "ESCALATED"


async def test_approval_timeout_resumes_offering() -> None:
    from app.db.models import ApprovalRequest

    world, _ = await build_world(floor_count=4)
    # Give emp_02 overtime exposure: 28h already worked this ISO week.
    from app.db.models import Shift
    from app.db.seed import DEMO_LOCATION_ID

    async with world.session_factory() as session:
        for day in (29, 30):
            base = datetime(2026, 9, day, 7, 0, tzinfo=UTC)
            session.add(
                Shift(
                    id=f"extra_{day}_am",
                    location_id=DEMO_LOCATION_ID,
                    role="floor",
                    starts_at=base,
                    ends_at=base + timedelta(hours=7),
                    employee_id="emp_02_floor",
                    status="scheduled",
                )
            )
            session.add(
                Shift(
                    id=f"extra_{day}_pm",
                    location_id=DEMO_LOCATION_ID,
                    role="floor",
                    starts_at=base + timedelta(hours=8),
                    ends_at=base + timedelta(hours=15),
                    employee_id="emp_02_floor",
                    status="scheduled",
                )
            )
        await session.commit()

    offers = await run_to_offering(world)
    overtime_offer = next(o for o in offers if o.employee_id == "emp_02_floor")
    assert overtime_offer.requires_approval
    await world.orchestrator.handle_inbound(
        conversation_id="conv_emp_02_floor",
        employee_id="emp_02_floor",
        provider_message_id="accept_ot",
        text="sí",
    )
    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "AWAITING_APPROVAL"

    # Approval timeout = case deadline.
    world.clock.advance(timedelta(minutes=12))
    await world.scheduler.run_due(world.clock.now())

    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "OFFERING"
        approval = (await session.execute(select(ApprovalRequest))).scalar_one()
        assert approval.status == "expired"


async def test_late_acceptance_after_escalation_goes_to_approval() -> None:
    world, _ = await build_world(floor_count=4)
    await run_to_offering(world)
    world.clock.advance(timedelta(minutes=12))
    await world.scheduler.run_due(world.clock.now())

    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "ESCALATED"

    # A candidate answers after the escalation.
    await world.orchestrator.handle_inbound(
        conversation_id="conv_emp_02_floor",
        employee_id="emp_02_floor",
        provider_message_id="late_accept",
        text="sí",
    )

    from app.db.models import ApprovalRequest

    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "AWAITING_APPROVAL"
        approval = (await session.execute(select(ApprovalRequest))).scalar_one()
        assert approval.status == "pending"
    manager_noticed = [m for m in world.channel.to_manager()]
    assert manager_noticed
