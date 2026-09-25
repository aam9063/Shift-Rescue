"""Deterministic message parser (spec §9.3 degraded mode).

Feature 2 stands in for the LLM interpreter: it only recognizes an explicit
confirmation/decline vocabulary and clear absence phrasing. Anything else is
UNCLEAR and must never trigger domain actions. Health details are never
extracted or stored here — redaction happens upstream (spec §10).
"""

import re
from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    CONFIRM = "CONFIRM"
    DECLINE = "DECLINE"
    ABSENCE_REPORT = "ABSENCE_REPORT"
    ABSENCE_RETRACT = "ABSENCE_RETRACT"
    UNCLEAR = "UNCLEAR"


@dataclass(frozen=True)
class ParsedMessage:
    intent: Intent
    confidence: float
    proposed_start: str | None = None  # "HH:MM" (degraded-mode conditional)
    proposed_end: str | None = None


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

_START_PATTERNS = [
    r"llego\s+a\s+las?\s+(\d{1,2})(?::(\d{2}))?(\s*y\s*(cuarto|media))?",
    r"puedo\s+desde\s+las?\s+(\d{1,2})(?::(\d{2}))?",
    r"a\s+partir\s+de\s+las?\s+(\d{1,2})(?::(\d{2}))?",
    r"sobre\s+las?\s+(\d{1,2})(?::(\d{2}))?",
]
_END_PATTERNS = [
    r"hasta\s+las?\s+(\d{1,2})(?::(\d{2}))?(\s*y\s*(cuarto|media))?",
    r"estoy\s+hasta\s+las?\s+(\d{1,2})(?::(\d{2}))?",
]
_DECLINE_EXTENDED = [
    r"al\s+final\s+no\b",
    r"no\s+puedo\s+al\s+final\b",
    r"tengo\s+que\s+cancelar\b",
    r"\bcancelo\b",
    r"no\s+podr\w*\b",
]
_RANGE_PATTERN = (
    r"de\s+(?:las?\s+)?(\d{1,2})(?::(\d{2}))?\s+a\s+(?:las?\s+)?(\d{1,2})(?::(\d{2}))?"
)


def _normalize(text: str) -> str:
    lowered = text.strip().lower()
    # Colons survive: they are meaningful for time extraction ("7:15").
    lowered = re.sub(r"[¡!¿?.,;]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _minutes_from(hour: int, minute: int, quarter_suffix: str | None) -> str | None:
    if quarter_suffix == "cuarto":
        minute = 15
    elif quarter_suffix == "media":
        minute = 30
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _extract_times(normalized: str) -> tuple[str | None, str | None]:
    """Degraded-mode conditional extraction: HH:MM strings or None."""
    proposed_start: str | None = None
    proposed_end: str | None = None

    range_match = re.search(_RANGE_PATTERN, normalized)
    if range_match:
        start_h, start_m, end_h, end_m = range_match.groups()
        proposed_start = _minutes_from(int(start_h), int(start_m or 0), None)
        proposed_end = _minutes_from(int(end_h), int(end_m or 0), None)
        if proposed_start and proposed_end:
            return proposed_start, proposed_end

    def first_match(pattern: str) -> tuple[int, int, str | None] | None:
        match = re.search(pattern, normalized)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        suffix = match.group(3) if match.re.groups >= 3 else None
        return hour, minute, suffix

    for pattern in _START_PATTERNS:
        found = first_match(pattern)
        if found:
            hour, minute, suffix = found
            quarter = suffix.strip().split()[-1] if suffix else None
            hour = hour + 12 if hour < 12 and "tarde" in normalized else hour
            proposed_start = _minutes_from(hour, minute, quarter)
            break
    for pattern in _END_PATTERNS:
        found = first_match(pattern)
        if found:
            hour, minute, suffix = found
            quarter = suffix.strip().split()[-1] if suffix else None
            proposed_end = _minutes_from(hour, minute, quarter)
            break
    return proposed_start, proposed_end


def parse_message(text: str) -> ParsedMessage:
    normalized = _normalize(text)
    words = set(normalized.split())

    if re.search(_RETRACT_PATTERN, normalized):
        return ParsedMessage(intent=Intent.ABSENCE_RETRACT, confidence=1.0)

    if any(re.search(pattern, normalized) for pattern in _ABSENCE_PATTERNS):
        return ParsedMessage(intent=Intent.ABSENCE_REPORT, confidence=0.95)

    if normalized in _CONFIRM_PHRASES or (words and words <= _CONFIRM_PHRASES):
        return ParsedMessage(intent=Intent.CONFIRM, confidence=1.0)

    proposed_start, proposed_end = _extract_times(normalized)
    if proposed_start or proposed_end:
        # Conditional acceptance with extracted times (spec §5.5).
        return ParsedMessage(
            intent=Intent.CONFIRM, confidence=0.9,
            proposed_start=proposed_start, proposed_end=proposed_end,
        )

    if any(re.search(pattern, normalized) for pattern in _DECLINE_EXTENDED):
        return ParsedMessage(intent=Intent.DECLINE, confidence=0.9)

    if normalized in _DECLINE_PHRASES or (words and words <= _DECLINE_PHRASES):
        return ParsedMessage(intent=Intent.DECLINE, confidence=1.0)

    # Single-word confirmations/declines mixed with noise stay UNCLEAR:
    # ambiguity never triggers actions (spec §5.5).
    return ParsedMessage(intent=Intent.UNCLEAR, confidence=0.0)
