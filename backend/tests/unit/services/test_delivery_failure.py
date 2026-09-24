"""Delivery failures must never break the orchestration (spec §5.5, §9.2)."""


from app.channels.twilio_whatsapp import TwilioChannelError
from tests.unit.services.helpers import build_world


class FlakyChannel:
    """Fails for one specific phone (e.g. a number that never joined the
    sandbox) and works for the rest."""

    def __init__(self, fail_for: str) -> None:
        self.fail_for = fail_for
        self.sent: list[dict] = []
        self.failures: list[str] = []

    async def send(self, recipient_phone_e164, body, *, template_key=None, rescue_id=None):
        if recipient_phone_e164 == self.fail_for:
            self.failures.append(recipient_phone_e164)
            raise TwilioChannelError("63016: recipient has not joined the sandbox")
        self.sent.append(
            {
                "to": recipient_phone_e164,
                "body": body,
                "template_key": template_key,
                "rescue_id": rescue_id,
            }
        )
        return f"prov_{len(self.sent)}"

    def with_template(self, template_key: str) -> list[dict]:
        return [m for m in self.sent if m["template_key"] == template_key]


async def test_failed_delivery_to_one_candidate_does_not_break_the_wave() -> None:
    world, _ = await build_world(floor_count=4)
    flaky = FlakyChannel(fail_for="+34600000002")  # emp_02's phone
    world.orchestrator._channel = flaky

    await world.orchestrator.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="p1",
        text="me encuentro fatal, hoy no puedo ir",
    )
    await world.orchestrator.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="p2",
        text="sí",
    )

    from sqlalchemy import select

    from app.db.models import AuditEvent, Offer, RescueCase

    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "OFFERING"  # orchestration survived

        offers = (await session.execute(select(Offer))).scalars().all()
        assert len(offers) == 3  # the other two are still offered
        failed = [o for o in offers if o.employee_id == "emp_02_floor"]
        assert failed and failed[0].status == "CANCELLED"

        audits = [a.type for a in (await session.execute(select(AuditEvent))).scalars()]
        assert "DELIVERY_FAILED" in audits

    assert len(flaky.with_template("offer")) == 2  # two delivered
    assert flaky.failures == ["+34600000002"]


async def test_all_waves_blocked_by_failures_still_escalate() -> None:
    world, _ = await build_world(floor_count=4)
    world.orchestrator._channel = FlakyChannel(fail_for="+34600000003")  # emp_03

    await world.orchestrator.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="p1",
        text="hoy no puedo ir",
    )
    await world.orchestrator.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="p2",
        text="sí",
    )

    async with world.session_factory() as session:
        from sqlalchemy import select

        from app.db.models import RescueCase

        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "OFFERING"


async def test_undeliverable_template_does_not_raise_from_the_webhook_path() -> None:
    """A provider rejection on a template send must not 500 the inbound path
    (Twilio would retry forever and the employee would get nothing)."""
    world, _ = await build_world(floor_count=4)
    world.orchestrator._channel = FlakyChannel(fail_for="+34600000001")

    handled = await world.orchestrator.handle_inbound(
        conversation_id="conv_1",
        employee_id="emp_01_floor",
        provider_message_id="p1",
        text="me encuentro fatal, hoy no puedo ir",
    )
    assert handled is None  # no exception

    from sqlalchemy import func, select

    from app.db.models import Message

    async with world.session_factory() as session:
        inbound = (
            await session.execute(
                select(func.count())
                .select_from(Message)
                .where(Message.direction == "inbound")
            )
        ).scalar_one()
        assert inbound == 1  # the message was still recorded
