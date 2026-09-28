"""JWT issue/verify for the dashboard API (spec §7.5).

HS256 with `settings.jwt_secret` and a TTL from `settings.jwt_expires_minutes`.
Verification is total: malformed, expired, tampered or wrongly-claimed tokens
answer `None` and the caller turns that into a 401.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings

ALGORITHM = "HS256"


@dataclass(frozen=True)
class TokenClaims:
    """The only claims the API relies on."""

    manager_id: str
    role: str


def issue_token(manager_id: str, role: str, settings: Settings) -> tuple[str, int]:
    """Issue an access token; returns (token, expires_in_seconds)."""
    expires_in = settings.jwt_expires_minutes * 60
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": manager_id,
            "role": role,
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )
    return token, expires_in


def verify_token(token: str, settings: Settings) -> TokenClaims | None:
    """Verify signature, expiry and claim types; None when anything fails."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    manager_id = payload.get("sub")
    role = payload.get("role")
    if not isinstance(manager_id, str) or not isinstance(role, str):
        return None
    return TokenClaims(manager_id=manager_id, role=role)
