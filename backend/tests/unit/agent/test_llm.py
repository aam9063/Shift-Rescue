"""Tests for StrandsLLMClient: breaker, metering, timeout and prompt assembly."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.agent.llm import CircuitBreaker, CircuitOpenError, StrandsLLMClient
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


class FakeAgent:
    def __init__(self, structured_output=None, fail_times: int = 0, delay: float = 0.0):
        self.structured_output = structured_output
        self.fail_times = fail_times
        self.delay = delay
        self.prompts: list[str] = []

    async def invoke_async(self, prompt: str):
        self.prompts.append(prompt)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise TimeoutError("provider timeout")
        if self.delay:
            await asyncio.sleep(self.delay)
        return self


def structured() -> Interpretation:
    return Interpretation(**VALID)


def test_circuit_opens_after_consecutive_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=3, reset_after=timedelta(seconds=60))
    now = datetime(2026, 10, 3, 14, 40, tzinfo=UTC)

    for _ in range(3):
        breaker.record_failure(now)
    assert breaker.is_open(now)


def test_circuit_resets_after_the_window() -> None:
    breaker = CircuitBreaker(failure_threshold=3, reset_after=timedelta(seconds=60))
    now = datetime(2026, 10, 3, 14, 40, tzinfo=UTC)
    for _ in range(3):
        breaker.record_failure(now)

    assert breaker.is_open(now + timedelta(seconds=30))
    assert not breaker.is_open(now + timedelta(seconds=61))


async def test_returns_validated_dict_and_records_usage() -> None:
    agent = FakeAgent(structured_output=structured())
    client = StrandsLLMClient(agent_factory=lambda: agent)

    result = await client.interpret("sí voy", {"rescue_id": "case_1"})

    assert result["intent"] == "OFFER_ACCEPT"
    assert client.last_usage is not None
    assert "sí voy" in agent.prompts[0]
    assert "case_1" in agent.prompts[0]


async def test_retries_transient_failures_then_succeeds() -> None:
    agent = FakeAgent(structured_output=structured(), fail_times=1)
    breaker = CircuitBreaker(failure_threshold=3, reset_after=timedelta(seconds=60))
    client = StrandsLLMClient(agent_factory=lambda: agent, breaker=breaker)

    result = await client.interpret("sí voy", {})

    assert result["intent"] == "OFFER_ACCEPT"
    assert len(agent.prompts) == 2
    assert not breaker.is_open(datetime.now(UTC))


async def test_open_circuit_fails_fast_without_calling_the_agent() -> None:
    agent = FakeAgent(structured_output=structured())
    breaker = CircuitBreaker(failure_threshold=1, reset_after=timedelta(seconds=60))
    client = StrandsLLMClient(agent_factory=lambda: agent, breaker=breaker)
    now = datetime(2026, 10, 3, 14, 40, tzinfo=UTC)
    breaker.record_failure(now)

    with pytest.raises(CircuitOpenError):
        await client.interpret("sí voy", {})

    assert agent.prompts == []


async def test_timeout_is_enforced(monkeypatch) -> None:
    agent = FakeAgent(structured_output=structured(), delay=5.0)
    client = StrandsLLMClient(agent_factory=lambda: agent, timeout_seconds=0.05)

    with pytest.raises(TimeoutError):
        await client.interpret("sí voy", {})
