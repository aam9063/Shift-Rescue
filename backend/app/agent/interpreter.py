"""Message interpreter (spec §6.2).

Wraps an LLMClient with strict validation: one retry including the
validation error, then a UNCLEAR fallback. Provider outages degrade
immediately to UNCLEAR — never block the rescue (spec §9.3).
"""

from typing import Any

from pydantic import ValidationError

from app.agent.schemas import Interpretation
from app.ports import LLMClient

PROMPT_VERSION = "interpreter_v4"

FALLBACK = Interpretation(intent="UNCLEAR", confidence=0.0)


class ProviderUnavailableError(Exception):
    """Provider outage/timeout: orchestrator degrades to the parser (§9.3)."""


class MessageInterpreter:
    def __init__(
        self,
        llm: LLMClient,
        *,
        prompt_version: str = PROMPT_VERSION,
        confidence_threshold: float = 0.75,
        max_retries: int = 1,
    ) -> None:
        self._llm = llm
        self.prompt_version = prompt_version
        self.confidence_threshold = confidence_threshold
        self._max_retries = max_retries

    async def interpret(self, message_body: str, context: dict[str, Any]) -> Interpretation:
        attempt_context = {**context, "prompt_version": self.prompt_version}
        last_error: str | None = None

        for _ in range(self._max_retries + 1):
            if last_error is not None:
                attempt_context = {**attempt_context, "validation_error": last_error}
            try:
                raw = await self._llm.interpret(message_body, attempt_context)
                # A real LLMClient returns the whole structured payload, which
                # already carries prompt_version; the interpreter owns it, so it
                # must overwrite rather than duplicate the keyword argument.
                return Interpretation(**{**raw, "prompt_version": self.prompt_version})
            except ValidationError as error:
                last_error = str(error)
            except Exception as error:
                # Provider outage/timeout: degrade to the parser (spec §9.3).
                raise ProviderUnavailableError(str(error)) from error

        return FALLBACK

    @property
    def last_usage(self) -> dict[str, Any] | None:
        """Usage dict of the wrapped client's last call, or None if unreported."""
        usage = getattr(self._llm, "last_usage", None)
        return usage if isinstance(usage, dict) else None
