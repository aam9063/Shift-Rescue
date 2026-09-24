"""Health-detail detection and redaction (spec §10).

Health content is redacted BEFORE persisting — it never reaches the manager,
logs or traces (invariant 7, §5.4).
"""

import re

_HEALTH_PATTERNS = [
    r"\benferm\w*",
    r"\bmigra\w*",
    r"\bfiebre\b",
    r"\bdolor\b",
    r"\bv[oó]mito\w*",
    r"\bgripe\b",
    r"\bcovid\b",
    r"\bmedicad\w*",
    r"\bhospital\b",
    r"\bm[eé]dico\b",
]

REDACTED_BODY = "[redacted: health details]"


def contains_health_details(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in _HEALTH_PATTERNS)


def redact_if_health(text: str) -> str:
    """Return the redacted placeholder when health content is present."""
    return REDACTED_BODY if contains_health_details(text) else text
