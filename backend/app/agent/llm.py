"""Strands-backed LLMClient (spec §6, §7.3).

Thin wrapper over the Strands Agents SDK (pinned 1.56.0): structured output,
timeout, retries, circuit breaker and token/cost metering with trace
attributes. The domain only knows the `LLMClient` protocol — Strands is
never imported outside this module.

The agent runs WITHOUT tools: the LLM interprets language, it never mutates
state (spec §6.1, ADR-002).
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.agent.schemas import Interpretation

DEFAULT_PRICE_PER_1K = {"input": 0.0008, "output": 0.004}  # USD, Claude Haiku class


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open — callers degrade to the parser."""


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_after: timedelta = timedelta(seconds=60)):
        self.failure_threshold = failure_threshold
        self.reset_after = reset_after
        self._consecutive_failures = 0
        self._opened_at: datetime | None = None

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._opened_at = now

    def is_open(self, now: datetime | None = None) -> bool:
        if self._opened_at is None:
            return False
        now = now or datetime.now(UTC)
        if now - self._opened_at > self.reset_after:
            self._opened_at = None
            self._consecutive_failures = 0
            return False
        return True


class StrandsLLMClient:
    """LLMClient implementation over a Strands Agent with structured output.

    `agent_factory` builds (or returns) the Strands Agent; injected fakes keep
    tests hermetic. Real wiring: `agent_factory=lambda: Agent(
    model=AnthropicModel(...), system_prompt=..., structured_output_model=
    Interpretation, callback_handler=None)` — no tools attached.
    """

    def __init__(
        self,
        agent_factory: Callable[[], Any],
        *,
        breaker: CircuitBreaker | None = None,
        timeout_seconds: float = 10.0,
        retries: int = 1,
        model_id: str = "claude-haiku-4-5",
        price_per_1k: dict[str, float] | None = None,
    ) -> None:
        self._agent_factory = agent_factory
        self.breaker = breaker or CircuitBreaker()
        self._timeout = timeout_seconds
        self._retries = retries
        self._model_id = model_id
        self._price = price_per_1k or DEFAULT_PRICE_PER_1K
        self.last_usage: dict[str, Any] | None = None

    async def interpret(self, message_body: str, context: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        if self.breaker.is_open(now):
            raise CircuitOpenError("LLM circuit open — degrade to deterministic parser")

        prompt = self._build_prompt(message_body, context)
        agent = self._agent_factory()

        result: Any = None
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                result = await asyncio.wait_for(agent.invoke_async(prompt), timeout=self._timeout)
                break
            except TimeoutError as error:
                last_error = error
            except Exception as error:  # transient provider failures retry once
                last_error = error
        else:
            self.breaker.record_failure(now)
            raise last_error if last_error else RuntimeError("LLM invocation failed")

        self.breaker.record_success()
        return self._extract(result)

    def _extract(self, result: Any) -> dict[str, Any]:
        structured = getattr(result, "structured_output", None)
        if structured is None:
            raise ValueError("Agent returned no structured output")
        if isinstance(structured, Interpretation):
            payload = structured.model_dump()
        elif isinstance(structured, dict):
            payload = Interpretation(**structured).model_dump()
        else:
            raise ValueError("Unexpected structured output type")
        self.last_usage = self._usage_of(result)
        return payload

    def _usage_of(self, result: Any) -> dict[str, Any]:
        metrics = getattr(result, "metrics", None)
        raw_usage = getattr(metrics, "usage", None) if metrics is not None else None
        input_tokens = float(getattr(raw_usage, "input_tokens", 0) or 0)
        output_tokens = float(getattr(raw_usage, "output_tokens", 0) or 0)
        latency = float(getattr(metrics, "total_cycle_time", 0) or 0)
        cost = (
            input_tokens / 1000 * self._price["input"]
            + output_tokens / 1000 * self._price["output"]
        )
        return {
            "model": self._model_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency,
            "cost_usd": cost,
        }

    def _build_prompt(self, message_body: str, context: dict[str, Any]) -> str:
        lines = [message_body]
        rescue_id = context.get("rescue_id")
        if rescue_id:
            lines.append(f"[rescue_id={rescue_id}]")
        pending = context.get("pending_offers")
        if pending:
            lines.append(f"[pending_offers={pending}]")
        shifts = context.get("shifts_48h")
        if shifts:
            lines.append(f"[shifts_48h={shifts}]")
        if context.get("validation_error"):
            lines.append(
                f"[Tu respuesta anterior no fue válida: {context['validation_error']}. "
                "Responde de nuevo con el formato correcto.]"
            )
        return "\n".join(lines)
