"""Orchestrator wiring: LLM interpreter first, deterministic parser fallback."""

import pytest
from sqlalchemy import select

from app.agent.interpreter import PROMPT_VERSION, MessageInterpreter
from app.agent.schemas import Interpretation
from app.db.models import ApprovalRequest, Offer, RescueCase
from app.db.models import Interpretation as InterpretationRow
from tests.unit.services.helpers import build_world, run_to_offering

CONVERSATION = "conv_1"


class ScriptedLLM:
    """Responds in call order; records the context of every call."""

    def __init__(self, responses: list[dict], usage: dict | None = None) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.contexts: list[dict] = []
        self.last_usage: dict | None = usage

    async def interpret(self, message_body: str, context: dict) -> dict:
        self.calls += 1
        self.contexts.append(dict(context))
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


class BrokenUsageLLM(ScriptedLLM):
    """Simulates a metering failure while persisting the interpretation."""

    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.contexts: list[dict] = []

    @property
    def last_usage(self) -> dict:  # type: ignore[override]
        raise RuntimeError("usage meter exploded")


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


async def test_llm_context_carries_accepted_offers_of_the_covering_employee() -> None:
    """After accepting, the employee's accepted offer reaches the model; before
    that, the same context carries an empty list (spec §5.5 withdrawal)."""
    world, _ = await build_world(floor_count=4)
    llm = ScriptedLLM(
        [
            {"intent": "ABSENCE_REPORT", "confidence": 0.95},
            {"intent": "ABSENCE_CONFIRM", "confidence": 0.98},
            {"intent": "OFFER_ACCEPT", "confidence": 0.98},
            {"intent": "OFFER_WITHDRAW", "confidence": 0.9},
        ]
    )
    world.orchestrator.interpreter = MessageInterpreter(llm=llm)
    offers = await run_to_offering(world)
    target = offers[0]

    await world.orchestrator.handle_inbound(
        conversation_id=f"conv_{target.employee_id}",
        employee_id=target.employee_id,
        provider_message_id="wires_ctx_1",
        text="vale si",
    )
    await world.orchestrator.handle_inbound(
        conversation_id=f"conv_{target.employee_id}",
        employee_id=target.employee_id,
        provider_message_id="wires_ctx_2",
        text="tengo que cancelar",
    )

    # Before acceptance: empty accepted_offers, pending offer present.
    assert llm.contexts[2]["accepted_offers"] == []
    assert llm.contexts[2]["pending_offers"] == [target.id]
    # After acceptance: the accepted offer is the marker.
    assert llm.contexts[3]["accepted_offers"] == [target.id]
    assert llm.contexts[3]["pending_offers"] == []
    # Existing context keys are untouched (plus the interpreter's prompt_version).
    assert {"rescue_id", "pending_offers", "accepted_offers"} <= set(llm.contexts[3])


async def test_llm_interpretation_is_persisted_with_measured_usage() -> None:
    world, _ = await build_world(floor_count=4)
    llm = ScriptedLLM(
        [
            {"intent": "ABSENCE_REPORT", "confidence": 0.95},
            {"intent": "ABSENCE_CONFIRM", "confidence": 0.98},
            {
                "intent": "OFFER_CONDITIONAL",
                "confidence": 0.9,
                "proposed_start": "2026-10-03T16:15:00+00:00",
                "proposed_end": "2026-10-03T21:00:00+00:00",
                "contains_health_details": False,
                "question_text": None,
            },
        ],
        usage={
            "model": "claude-haiku-4-5",
            "input_tokens": 120,
            "output_tokens": 30,
            "latency_ms": 511.5,
            "cost_usd": 0.0002,
        },
    )
    world.orchestrator.interpreter = MessageInterpreter(llm=llm)
    offers = await run_to_offering(world)
    target = offers[0]

    await world.orchestrator.handle_inbound(
        conversation_id=f"conv_{target.employee_id}",
        employee_id=target.employee_id,
        provider_message_id="wires_persist_1",
        text="llego a las 17:15",
    )

    async with world.session_factory() as session:
        rows = (await session.execute(select(InterpretationRow))).scalars().all()
    assert len(rows) == 3  # one row per LLM interpretation
    row = rows[-1]
    assert row.intent == "OFFER_CONDITIONAL"
    assert row.confidence == pytest.approx(0.9)
    assert row.model == "claude-haiku-4-5"
    assert row.prompt_version == PROMPT_VERSION
    assert row.latency_ms == 511
    assert row.input_tokens == 120
    assert row.output_tokens == 30
    assert row.cost_usd == pytest.approx(0.0002)
    # Structured fields only: no message body, no health narrative (§10).
    assert set(row.extracted) == {
        "shift_reference",
        "offer_reference",
        "proposed_start",
        "proposed_end",
        "contains_health_details",
        "question_text",
    }
    assert row.extracted["proposed_start"] == "2026-10-03T16:15:00+00:00"
    assert "17:15" not in str(row.extracted)


async def test_llm_interpretation_defaults_to_zero_usage_when_unreported() -> None:
    world, _ = await build_world(floor_count=4)
    world.orchestrator.interpreter = interpreter_with(
        {"intent": "UNCLEAR", "confidence": 0.3}
    )

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_02_floor",
        provider_message_id="wires_persist_2",
        text="mm",
    )

    async with world.session_factory() as session:
        rows = (await session.execute(select(InterpretationRow))).scalars().all()
    assert len(rows) == 1
    assert rows[0].model == "unknown"
    assert rows[0].input_tokens == 0
    assert rows[0].output_tokens == 0
    assert rows[0].cost_usd == 0.0


async def test_parser_path_persists_no_interpretation_rows() -> None:
    world, _ = await build_world(floor_count=4)
    world.orchestrator.interpreter = OpenBreakerInterpreter()

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="wires_persist_3",
        text="me encuentro fatal, hoy no puedo ir",
    )
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="wires_persist_4",
        text="sí",
    )

    async with world.session_factory() as session:
        rows = (await session.execute(select(InterpretationRow))).scalars().all()
    assert rows == []


async def test_no_interpreter_persists_no_interpretation_rows() -> None:
    world, _ = await build_world(floor_count=4)

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_01_floor",
        provider_message_id="wires_persist_5",
        text="me encuentro fatal, hoy no puedo ir",
    )

    async with world.session_factory() as session:
        rows = (await session.execute(select(InterpretationRow))).scalars().all()
    assert rows == []


async def test_duplicate_provider_message_persists_no_second_row() -> None:
    world, _ = await build_world(floor_count=4)
    world.orchestrator.interpreter = interpreter_with(
        {"intent": "UNCLEAR", "confidence": 0.3}
    )

    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_02_floor",
        provider_message_id="wires_persist_6",
        text="mm",
    )
    await world.orchestrator.handle_inbound(
        conversation_id=CONVERSATION,
        employee_id="emp_02_floor",
        provider_message_id="wires_persist_6",
        text="mm",
    )

    async with world.session_factory() as session:
        rows = (await session.execute(select(InterpretationRow))).scalars().all()
    assert len(rows) == 1


async def test_persistence_failure_is_logged_and_flow_continues() -> None:
    world, _ = await build_world(floor_count=4)
    world.orchestrator.interpreter = MessageInterpreter(
        llm=BrokenUsageLLM(
            [
                {"intent": "ABSENCE_REPORT", "confidence": 0.95},
                {"intent": "ABSENCE_CONFIRM", "confidence": 0.98},
                {"intent": "OFFER_ACCEPT", "confidence": 0.98},
            ]
        )
    )
    offers = await run_to_offering(world)
    target = offers[0]

    await world.orchestrator.handle_inbound(
        conversation_id=f"conv_{target.employee_id}",
        employee_id=target.employee_id,
        provider_message_id="wires_persist_7",
        text="vale si",
    )

    # The rescue flow survived the persistence failure.
    async with world.session_factory() as session:
        case = (await session.execute(select(RescueCase))).scalar_one()
        assert case.status == "COVERED"
        rows = (await session.execute(select(InterpretationRow))).scalars().all()
    assert rows == []
