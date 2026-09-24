"""Message interpreter (spec §6.2).

Wraps an LLMClient with strict validation: one retry including the
validation error, then a UNCLEAR fallback. Provider outages degrade
immediately to UNCLEAR — never block the rescue (spec §9.3).
"""

from typing import Any

from pydantic import ValidationError

from app.agent.schemas import Interpretation
from app.ports import LLMClient

FALLBACK = Interpretation(intent="UNCLEAR", confidence=0.0)


class MessageInterpreter:
    def __init__(
        self,
        llm: LLMClient,
        *,
        prompt_version: str = "interpreter_v1",
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
                return Interpretation(
                    **raw, prompt_version=self.prompt_version
                ).model_copy()
            except ValidationError as error:
                last_error = str(error)
            except Exception:
                # Provider outage/timeout: degrade immediately (spec §9.3).
                return FALLBACK

        return FALLBACK
