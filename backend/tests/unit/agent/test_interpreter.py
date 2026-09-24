"""Tests for the Interpretation schema and interpreter core (spec §6.2)."""


import pytest
from pydantic import ValidationError

from app.agent.interpreter import MessageInterpreter
from app.agent.schemas import Interpretation

VALID = {
    "intent": "OFFER_ACCEPT",
    "confidence": 0.97,
    "shift_reference": "shift_1",
    "offer_reference": "offer_1",
    "proposed_start": None,
    "proposed_end": None,
    "contains_health_details": False,
    "question_text": None,
}


class FakeLLM:
    def __init__(self, responses: list[dict | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    async def interpret(self, message_body: str, context: dict) -> dict:
        self.calls.append((message_body, context))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_interpretation_schema_rejects_unknown_intent() -> None:
    with pytest.raises(ValidationError):
        Interpretation(**{**VALID, "intent": "MAKE_ME_A_SANDWICH"})


def test_interpretation_schema_rejects_confidence_out_of_range() -> None:
    with pytest.raises(ValidationError):
        Interpretation(**{**VALID, "confidence": 1.5})


async def test_valid_response_is_validated_and_returned() -> None:
    llm = FakeLLM([VALID])
    interpreter = MessageInterpreter(llm=llm)

    result = await interpreter.interpret("sí voy", {"rescue_id": "case_1"})

    assert isinstance(result, Interpretation)
    assert result.intent == "OFFER_ACCEPT"
    assert result.confidence == 0.97
    assert result.prompt_version == "interpreter_v1"
    assert llm.calls[0][1]["rescue_id"] == "case_1"


async def test_invalid_output_retried_once_with_validation_error() -> None:
    llm = FakeLLM([{**VALID, "intent": "NOPE"}, VALID])
    interpreter = MessageInterpreter(llm=llm)

    result = await interpreter.interpret("sí voy", {})

    assert result.intent == "OFFER_ACCEPT"
    assert len(llm.calls) == 2
    assert "validation_error" in llm.calls[1][1]


async def test_two_invalid_outputs_fall_back_to_unclear() -> None:
    llm = FakeLLM([{**VALID, "intent": "NOPE"}, {**VALID, "confidence": 7}])
    interpreter = MessageInterpreter(llm=llm)

    result = await interpreter.interpret("sí voy", {})

    assert result.intent == "UNCLEAR"
    assert result.confidence == 0.0
    assert len(llm.calls) == 2


async def test_llm_exception_falls_back_to_unclear_without_retry() -> None:
    llm = FakeLLM([TimeoutError("provider down"), VALID])
    interpreter = MessageInterpreter(llm=llm)

    result = await interpreter.interpret("sí voy", {})

    assert result.intent == "UNCLEAR"
    assert len(llm.calls) == 1  # exceptions degrade immediately (§9.3)


async def test_health_details_flag_passes_through() -> None:
    llm = FakeLLM([{**VALID, "intent": "ABSENCE_REPORT", "contains_health_details": True}])
    interpreter = MessageInterpreter(llm=llm)

    result = await interpreter.interpret("estoy enfermo", {})

    assert result.contains_health_details is True


async def test_low_confidence_is_returned_untouched_for_caller_decision() -> None:
    llm = FakeLLM(
        [{**VALID, "intent": "QUESTION", "confidence": 0.4, "question_text": "¿a qué hora?"}]
    )
    interpreter = MessageInterpreter(llm=llm, confidence_threshold=0.75)

    result = await interpreter.interpret("¿a qué hora era?", {})

    assert result.intent == "QUESTION"
    assert result.confidence == 0.4
    assert interpreter.confidence_threshold == 0.75
