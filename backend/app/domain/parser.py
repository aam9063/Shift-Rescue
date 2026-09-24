"""Deterministic message parser (spec §9.3 degraded mode).

Feature 2 stands in for the LLM interpreter: it only recognizes an explicit
confirmation/decline vocabulary and clear absence phrasing. Anything else is
UNCLEAR and must never trigger domain actions. Health details are never
extracted or stored here — redaction happens upstream (spec §10).
"""

import re
from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    CONFIRM = "CONFIRM"
    DECLINE = "DECLINE"
    ABSENCE_REPORT = "ABSENCE_REPORT"
    ABSENCE_RETRACT = "ABSENCE_RETRACT"
    UNCLEAR = "UNCLEAR"


@dataclass(frozen=True)
class ParsedMessage:
    intent: Intent
    confidence: float


_CONFIRM_PHRASES = {"si", "sí", "vale", "ok", "okey", "1", "confirmo", "voy", "ahí", "alli", "👍"}
_DECLINE_PHRASES = {"no", "nop", "2", "no gracias"}
# Phrases that express the employee will miss the shift (absence report).
_ABSENCE_PATTERNS = [
    r"\bno\s+puedo\s+ir\b",
    r"\bno\s+voy\s+a\s+poder\s+ir\b",
    r"\bno\s+voy\s+hoy\b",
    r"\bno\s+llego\b",
    r"\bme\s+encuentro\s+(mal|fatal)\b",
    r"\bme\s+he\s+levantado\s+fatal\b",
    r"\bestoy\s+enferm\w*\b",
]
_RETRACT_PATTERN = r"\bal\s+final\s+(s[ií]\s+)?puedo\s+ir\b"


def _normalize(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[¡!¿?.,;:]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def parse_message(text: str) -> ParsedMessage:
    normalized = _normalize(text)
    words = set(normalized.split())

    if re.search(_RETRACT_PATTERN, normalized):
        return ParsedMessage(intent=Intent.ABSENCE_RETRACT, confidence=1.0)

    if any(re.search(pattern, normalized) for pattern in _ABSENCE_PATTERNS):
        return ParsedMessage(intent=Intent.ABSENCE_REPORT, confidence=0.95)

    if normalized in _CONFIRM_PHRASES or (words and words <= _CONFIRM_PHRASES):
        return ParsedMessage(intent=Intent.CONFIRM, confidence=1.0)

    if normalized in _DECLINE_PHRASES or (words and words <= _DECLINE_PHRASES):
        return ParsedMessage(intent=Intent.DECLINE, confidence=1.0)

    # Single-word confirmations/declines mixed with noise stay UNCLEAR:
    # ambiguity never triggers actions (spec §5.5).
    return ParsedMessage(intent=Intent.UNCLEAR, confidence=0.0)
