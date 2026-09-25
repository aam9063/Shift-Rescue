"""Validated LLM output schemas (spec §6.2).

Every LLM output is validated with Pydantic before the domain uses it —
the LLM proposes, the domain disposes.
"""

from typing import Literal

from pydantic import BaseModel, Field

IntentName = Literal[
    "ABSENCE_REPORT",
    "ABSENCE_CONFIRM",
    "ABSENCE_RETRACT",
    "OFFER_ACCEPT",
    "OFFER_DECLINE",
    "OFFER_CONDITIONAL",
    "OFFER_WITHDRAW",
    "QUESTION",
    "SMALLTALK",
    "UNCLEAR",
]


class Interpretation(BaseModel):
    intent: IntentName
    confidence: float = Field(ge=0.0, le=1.0)
    shift_reference: str | None = None
    offer_reference: str | None = None
    proposed_start: str | None = None  # ISO-8601 when OFFER_CONDITIONAL
    proposed_end: str | None = None
    contains_health_details: bool = False
    question_text: str | None = None
    prompt_version: str = "interpreter_v1"
