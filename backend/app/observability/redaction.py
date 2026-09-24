"""Privacy helpers (spec §9.1, §10): phone masking for logs/traces and
health-detail redaction BEFORE persistence (invariant 7, §5.4)."""

import re

_PHONE_PATTERN = re.compile(r"^(\+?)(\d{2})(\d+)(\d{2})$")


def mask_phone(phone: str) -> str:
    """'+34600000001' -> '+34*******01'; garbage passes through."""
    match = _PHONE_PATTERN.match(phone.strip())
    if not match:
        return phone
    plus, prefix, middle, last = match.groups()
    return f"{plus}{prefix}{'*' * len(middle)}{last}"


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
