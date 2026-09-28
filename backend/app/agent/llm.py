"""Strands-backed LLMClient (spec §6, §7.3).

Thin wrapper over the Strands Agents SDK (pinned 1.56.0): structured output,
timeout, retries, circuit breaker and token/cost metering with trace
attributes. The domain only knows the `LLMClient` protocol — Strands is
never imported outside this module.

The agent runs WITHOUT tools: the LLM interprets language, it never mutates
state (spec §6.1, ADR-002).
"""

import asyncio
import time
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

        started = time.perf_counter()
        result: Any = None
        last_error: Exception | None = None
        for _attempt in range(self._retries + 1):
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

        elapsed_ms = (time.perf_counter() - started) * 1000
        self.breaker.record_success()
        return self._extract(result, elapsed_ms)

    def _extract(self, result: Any, elapsed_ms: float) -> dict[str, Any]:
        structured = getattr(result, "structured_output", None)
        if structured is None:
            raise ValueError("Agent returned no structured output")
        if isinstance(structured, Interpretation):
            payload = structured.model_dump()
        elif isinstance(structured, dict):
            payload = Interpretation(**structured).model_dump()
        else:
            raise ValueError("Unexpected structured output type")
        self.last_usage = self._usage_of(result, elapsed_ms)
        return payload

    def _usage_of(self, result: Any, elapsed_ms: float) -> dict[str, Any]:
        """Token/latency/cost metering (spec §9.2).

        Strands 1.56 reports `EventLoopMetrics.accumulated_usage` with
        camelCase keys and `accumulated_metrics['latencyMs']`; the snake_case
        names of earlier versions are still accepted. Wall-clock time is the
        fallback because the SDK reports 0 for latency in some releases.
        """
        metrics = getattr(result, "metrics", None)
        raw_usage = (
            getattr(metrics, "accumulated_usage", None)
            or getattr(metrics, "usage", None)
            or {}
        )

        def token(*names: str) -> float:
            for name in names:
                value = raw_usage.get(name) if isinstance(raw_usage, dict) else None
                if value:
                    return float(value)
            return 0.0

        input_tokens = token("inputTokens", "input_tokens")
        output_tokens = token("outputTokens", "output_tokens")
        cached_input_tokens = token("cacheReadInputTokens", "cache_read_input_tokens")
        provider_latency = 0.0
        accumulated = getattr(metrics, "accumulated_metrics", None)
        if isinstance(accumulated, dict):
            provider_latency = float(accumulated.get("latencyMs", 0) or 0)
        # Cached reads are billed at a discount by the provider but counted at
        # full price here: the number is a conservative upper bound.
        cost = (
            input_tokens / 1000 * self._price["input"]
            + output_tokens / 1000 * self._price["output"]
        )
        return {
            "model": self._model_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": cached_input_tokens,
            "latency_ms": provider_latency or round(elapsed_ms, 1),
            "cost_usd": cost,
        }

    def _build_prompt(self, message_body: str, context: dict[str, Any]) -> str:
        lines = [message_body]
        for key in ("rescue_id", "pending_offers", "pending_confirmation", "shifts_48h"):
            value = context.get(key)
            if value:
                lines.append(f"[{key}={value}]")
        # The golden set and the orchestrator may carry extra context; drop
        # nothing silently — render any remaining non-empty string/list. Keys
        # that look like credentials are never forwarded (secrets stay out of
        # prompts).
        secret_hints = ("secret", "token", "password", "api_key", "authorization")
        for key, value in context.items():
            if key in ("rescue_id", "pending_offers", "pending_confirmation", "shifts_48h"):
                continue
            if key == "validation_error":
                continue
            if any(hint in key.lower() for hint in secret_hints):
                continue
            if isinstance(value, (str, list)) and value:
                lines.append(f"[{key}={value}]")
        if context.get("validation_error"):
            lines.append(
                f"[Tu respuesta anterior no fue válida: {context['validation_error']}. "
                "Responde de nuevo con el formato correcto.]"
            )
        return "\n".join(lines)
