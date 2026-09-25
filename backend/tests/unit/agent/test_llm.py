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


class FakeMetrics:
    """Shape reported by Strands 1.56: EventLoopMetrics with camelCase usage."""

    def __init__(self, usage: dict, latency_ms: float = 0.0) -> None:
        self.accumulated_usage = usage
        self.accumulated_metrics = {"latencyMs": latency_ms}


class FakeAgentWithMetrics(FakeAgent):
    def __init__(self, *args, usage: dict | None = None, latency_ms: float = 0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics = FakeMetrics(
            usage
            if usage is not None
            else {"inputTokens": 1126, "outputTokens": 56, "cacheReadInputTokens": 1024},
            latency_ms,
        )


async def test_meters_the_real_strands_metrics_shape() -> None:
    agent = FakeAgentWithMetrics(structured_output=structured())
    client = StrandsLLMClient(
        agent_factory=lambda: agent,
        model_id="gpt-4o-mini",
        price_per_1k={"input": 0.00015, "output": 0.0006},
    )

    await client.interpret("sí voy", {})

    usage = client.last_usage or {}
    assert usage["input_tokens"] == 1126
    assert usage["output_tokens"] == 56
    assert usage["cached_input_tokens"] == 1024
    # 1126/1000*0.00015 + 56/1000*0.0006 = 0.0001689 + 0.0000336
    assert usage["cost_usd"] == pytest.approx(0.0002025, rel=1e-3)
    assert usage["model"] == "gpt-4o-mini"


async def test_latency_falls_back_to_wall_clock_when_the_sdk_reports_zero() -> None:
    # A tiny delay makes the wall-clock fallback observable (an instant call
    # legitimately measures ~0 ms).
    agent = FakeAgentWithMetrics(structured_output=structured(), latency_ms=0.0, delay=0.01)
    client = StrandsLLMClient(agent_factory=lambda: agent)

    await client.interpret("sí voy", {})

    assert (client.last_usage or {})["latency_ms"] > 0


async def test_meters_legacy_snake_case_usage_shape() -> None:
    class LegacyMetrics:
        usage = {"input_tokens": 100, "output_tokens": 10}
        accumulated_metrics = {"latencyMs": 0}

    agent = FakeAgent(structured_output=structured())
    agent.metrics = LegacyMetrics()
    client = StrandsLLMClient(agent_factory=lambda: agent)

    await client.interpret("sí voy", {})

    usage = client.last_usage or {}
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 10
    assert usage["cached_input_tokens"] == 0
