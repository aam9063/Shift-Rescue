"""Shared FastAPI dependencies for the dashboard API (spec §7.5).

`current_manager` enforces the bearer token (401 when missing, malformed,
expired or tampered); `require_role` narrows routes by manager role (403 when
the role does not match). Settings and the DB session are dependency-injected
so tests can override them.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.security.tokens import verify_token

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ManagerPrincipal:
    """Identity carried by a valid access token."""

    manager_id: str
    role: str


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_manager(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> ManagerPrincipal:
    """Require a valid bearer token; 401 on anything else."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    claims = verify_token(credentials.credentials, settings)
    if claims is None:
        raise _unauthorized()
    return ManagerPrincipal(manager_id=claims.manager_id, role=claims.role)


def require_role(*allowed_roles: str) -> Callable[[ManagerPrincipal], Awaitable[ManagerPrincipal]]:
    """Dependency factory: keep `current_manager` and check the role (403)."""

    async def dependency(
        principal: ManagerPrincipal = Depends(current_manager),
    ) -> ManagerPrincipal:
        if principal.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return principal

    return dependency


# Re-exported so routers (and tests) import one consistent session dependency.
get_db = get_session
__all__ = ["ManagerPrincipal", "current_manager", "get_db", "require_role"]
