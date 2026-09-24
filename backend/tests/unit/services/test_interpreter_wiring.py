"""Orchestrator wiring: LLM interpreter first, deterministic parser fallback."""


from sqlalchemy import select

from app.agent.interpreter import MessageInterpreter
from app.agent.schemas import Interpretation
from app.db.models import ApprovalRequest, Offer, RescueCase
from tests.unit.services.helpers import build_world, run_to_offering

CONVERSATION = "conv_1"


class ScriptedLLM:
    """Responds in call order; ideal for multi-step flows."""

    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def interpret(self, message_body: str, context: dict) -> dict:
        self.calls += 1
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


def interpreter_with(response: dict) -> MessageInterpreter:
    return MessageInterpreter(llm=ScriptedLLM([response]))


class OpenBreakerInterpreter(MessageInterpreter):
    """Interpreter whose provider raises CircuitOpenError (degraded mode)."""

    def __init__(self) -> None:
        super().__init__(llm=ScriptedLLM([]))

    async def interpret(self, message_body: str, context: dict) -> Interpretation:
        from app.agent.llm import CircuitOpenError

        raise CircuitOpenError("open")


async def test_llm_offer_accept_routes_to_acceptance() -> None:
    world, _ = await build_world(floor_count=4)
    world.orchestrator.interpreter = MessageInterpreter(
        llm=ScriptedLLM(
            [
                {"intent": "ABSENCE_REPORT", "confidence": 0.95},
                {"intent": "ABSENCE_CONFIRM", "confidence": 0.98},
                {"intent": "OFFER_ACCEPT", "confidence": 0.98, "offer_reference": "offer_1"},
            ]
        )
    )
    offers = await run_to_offering(world)
    target = offers[0]

    await world.orchestrator.handle_inbound(
        conversation_id=f"conv_{target.employee_id}",
        employee_id=target.employee_id,
        provider_message_id="wires_1",
        text="vale si",
    )

    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "COVERED"
        assert case.covering_employee_id == target.employee_id


async def test_llm_unclear_sends_single_clarification() -> None:
    world, _ = await build_world(floor_count=4)
    world.orchestrator.interpreter = interpreter_with(
        {"intent": "UNCLEAR", "confidence": 0.3, "question_text": None}
    )
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_02_floor",
        provider_message_id="wires_2",
        text="igual si luego te digo",
    )
    clarifications = world.channel.with_template("ask_clarification")
    assert len(clarifications) == 1

    # A second UNCLEAR does not spam: redirects politely instead.
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_02_floor",
        provider_message_id="wires_3",
        text="mm",
    )
    clarifications = world.channel.with_template("ask_clarification")
    assert len(clarifications) == 1
    assert world.channel.with_template("out_of_scope")


async def test_circuit_open_falls_back_to_deterministic_parser() -> None:
    world, _ = await build_world(floor_count=4)
    world.orchestrator.interpreter = OpenBreakerInterpreter()

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="wires_4",
        text="me encuentro fatal, hoy no puedo ir",
    )

    confirms = world.channel.with_template("absence_confirm")
    assert confirms  # parser path handled the report
    from sqlalchemy import func

    from app.db.models import Message

    async with world.session_factory() as session:
        inbound = (
            await session.execute(
                select(func.count()).select_from(Message).where(Message.direction == "inbound")
            )
        ).scalar_one()
    assert inbound == 1  # no LLM call happened (OpenBreakerInterpreter.llm.calls == 0)


async def test_llm_conditional_accept_creates_partial_coverage_approval() -> None:
    world, _ = await build_world(floor_count=4)
    world.orchestrator.interpreter = MessageInterpreter(
        llm=ScriptedLLM(
            [
                {"intent": "ABSENCE_REPORT", "confidence": 0.95},
                {"intent": "ABSENCE_CONFIRM", "confidence": 0.98},
                {
                    "intent": "OFFER_CONDITIONAL",
                    "confidence": 0.9,
                    "proposed_start": "2026-10-03T16:15:00+00:00",
                    "proposed_end": "2026-10-03T21:00:00+00:00",
                },
            ]
        )
    )
    offers = await run_to_offering(world)
    target = offers[0]

    await world.orchestrator.handle_inbound(
        conversation_id=f"conv_{target.employee_id}",
        employee_id=target.employee_id,
        provider_message_id="wires_5",
        text="llego a las 17:15",
    )

    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "AWAITING_APPROVAL"
        approval = (await session.execute(select(ApprovalRequest))).scalar_one()
        assert approval.kind == "partial_coverage"
        offer = (await session.execute(select(Offer).where(Offer.id == target.id))).scalar_one()
        assert offer.proposed_start is not None
        assert offer.proposed_end is not None


async def test_no_interpreter_keeps_parser_behavior() -> None:
    world, _ = await build_world(floor_count=4)
    assert world.orchestrator.interpreter is None

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="wires_6",
        text="me encuentro fatal, hoy no puedo ir",
    )
    assert world.channel.with_template("absence_confirm")
