"""Acceptance resolution tests (spec §2.6, §5.5, §7.4)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.seed import DEMO_LOCATION_ID
from tests.unit.services.test_orchestrator import (  # noqa: F401
    CONVERSATION,
    PROVIDER_ID,
)


async def _run_to_offering(world) -> list["OfferLike"]:
    """Drive report + confirmation; return the pending offers."""
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
    async with world.session_factory() as session:
        return sorted(
            (await session.execute(select(OfferLike))).scalars(), key=lambda o: o.employee_id
        )


from app.db.models import Offer as OfferLike  # noqa: E402


async def _accept(world, employee_id: str, provider_id: str) -> None:
    await world.orchestrator.handle_inbound(
        conversation_id=f"conv_{employee_id}",
        employee_id=employee_id,
        provider_message_id=provider_id,
        text="sí",
    )


class TestUnconditionalAccept:
    async def test_accept_covers_shift_and_cancels_others(self, world, db) -> None:
        offers = await _run_to_offering(world)
        winner = offers[0]  # emp_02_floor

        await _accept(world, winner.employee_id, "accept_1")

        from app.db.models import RescueCase, Shift

        async with db() as session:
            case = (await session.execute(select(RescueCase))).scalar_one()
            assert case.status == "COVERED"
            assert case.covering_employee_id == winner.employee_id
            assert case.closed_at is not None

            shift = (await session.execute(select(Shift).where(Shift.id == "shift_1"))).scalar_one()
            assert shift.status == "covered"
            assert shift.employee_id == winner.employee_id

            offers_after = sorted(
                (await session.execute(select(OfferLike))).scalars(), key=lambda o: o.employee_id
            )
            accepted = [o for o in offers_after if o.status == "ACCEPTED"]
            cancelled = [o for o in offers_after if o.status == "CANCELLED"]
            assert len(accepted) == 1 and accepted[0].employee_id == winner.employee_id
            assert len(cancelled) == 2

    async def test_winner_gets_confirmation_manager_gets_notice(self, world) -> None:
        offers = await _run_to_offering(world)
        await _accept(world, offers[0].employee_id, "accept_1")

        confirmed = [m for m in world.channel.sent if m["template_key"] == "offer_confirmed"]
        assert confirmed and confirmed[0]["to"] == "+34600000002"
        assert any(m["to"] == "+34600999001" for m in world.channel.sent)

    async def test_loser_receives_already_covered(self, world) -> None:
        offers = await _run_to_offering(world)
        await _accept(world, offers[0].employee_id, "accept_1")
        await _accept(world, offers[1].employee_id, "accept_2")

        covered_msgs = [
            m for m in world.channel.sent if m["template_key"] == "offer_already_covered"
        ]
        assert covered_msgs and covered_msgs[0]["to"] == "+34600000003"
        from app.db.models import RescueCase

        async with world.session_factory() as session:
            case = (await session.execute(select(RescueCase))).scalar_one()
            assert case.status == "COVERED"


class TestOvertimeApproval:
    @pytest.fixture()
    async def overtime_world(self, world, db, now):
        """emp_02 has 28h already worked this week -> their offer needs approval."""

        async with db() as session:
            # 28h worked this ISO week: +8h target = 36h -> over the 30h
            # contract, under the 40h hard cap -> overtime approval required.
            for day in (29, 30):
                session.add(_week_shift(now, f"extra_{day}_am", day, 7, 14, "emp_02_floor"))
                session.add(_week_shift(now, f"extra_{day}_pm", day, 15, 22, "emp_02_floor"))
            await session.commit()
        return world

    async def test_overtime_accept_awaits_approval(self, overtime_world, db) -> None:
        offers = await _run_to_offering(overtime_world)
        overtime_offer = next(o for o in offers if o.employee_id == "emp_02_floor")
        assert overtime_offer.requires_approval

        await _accept(overtime_world, "emp_02_floor", "accept_ot")

        from app.db.models import ApprovalRequest, RescueCase, Shift

        async with db() as session:
            case = (await session.execute(select(RescueCase))).scalar_one()
            assert case.status == "AWAITING_APPROVAL"
            approval = (await session.execute(select(ApprovalRequest))).scalar_one()
            assert approval.kind == "overtime"
            assert approval.status == "pending"
            shift = (await session.execute(select(Shift).where(Shift.id == "shift_1"))).scalar_one()
            assert shift.status == "absent"  # not assigned until approved

        pending = [
            m for m in overtime_world.channel.sent if m["template_key"] == "offer_pending_approval"
        ]
        assert pending

    async def test_manager_approval_covers(self, overtime_world, db) -> None:
        await _run_to_offering(overtime_world)
        await _accept(overtime_world, "emp_02_floor", "accept_ot")

        from app.db.models import ApprovalRequest

        async with db() as session:
            approval = (await session.execute(select(ApprovalRequest))).scalar_one()

        await overtime_world.orchestrator.decide_approval(
            approval.id, "approved", "mgr_1"
        )

        from app.db.models import RescueCase, Shift

        async with db() as session:
            case = (await session.execute(select(RescueCase))).scalar_one()
            assert case.status == "COVERED"
            assert case.covering_employee_id == "emp_02_floor"
            shift = (await session.execute(select(Shift).where(Shift.id == "shift_1"))).scalar_one()
            assert shift.employee_id == "emp_02_floor"
            approval = (await session.execute(select(ApprovalRequest))).scalar_one()
            assert approval.status == "approved"

    async def test_manager_rejection_resumes_offering(self, overtime_world, db) -> None:
        await _run_to_offering(overtime_world)
        await _accept(overtime_world, "emp_02_floor", "accept_ot")

        from app.db.models import ApprovalRequest

        async with db() as session:
            approval = (await session.execute(select(ApprovalRequest))).scalar_one()
        await overtime_world.orchestrator.decide_approval(approval.id, "rejected", "mgr_1")

        from app.db.models import RescueCase

        async with db() as session:
            case = (await session.execute(select(RescueCase))).scalar_one()
            assert case.status == "OFFERING"
            approval = (await session.execute(select(ApprovalRequest))).scalar_one()
            assert approval.status == "rejected"


class TestExpiredAndDeclined:
    async def test_decline_marks_offer_and_keeps_offering(self, world) -> None:
        offers = await _run_to_offering(world)
        await world.orchestrator.handle_inbound(
            conversation_id=f"conv_{offers[0].employee_id}",
            employee_id=offers[0].employee_id,
            provider_message_id="decline_1",
            text="no",
        )

        async with world.session_factory() as session:
            refreshed = await session.get(OfferLike, offers[0].id)
            assert refreshed.status == "DECLINED"
        from app.db.models import RescueCase

        async with world.session_factory() as session:
            case = (await session.execute(select(RescueCase))).scalar_one()
            assert case.status == "OFFERING"


def _week_shift(now: datetime, shift_id: str, day: int, start_h: int, end_h: int, employee_id: str):
    from app.db.models import Shift

    base = datetime(2026, 9, day, start_h, 0, tzinfo=UTC)
    return Shift(
        id=shift_id,
        location_id=DEMO_LOCATION_ID,
        role="floor",
        starts_at=base,
        ends_at=datetime(2026, 9, day, end_h, 0, tzinfo=UTC),
        employee_id=employee_id,
        status="scheduled",
    )
