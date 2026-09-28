"""Manager login (spec §7.5): `POST /api/auth/login`.

Verifies the Argon2 hash of the seeded manager and issues an HS256 JWT.
Failures are a single generic 401 — never reveals whether the email exists.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.config import Settings, get_settings
from app.db.models import Manager
from app.schemas.dashboard import LoginResponse, ManagerOut
from app.security.passwords import verify_password
from app.security.tokens import issue_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Invalid email or password"


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    manager = (
        await session.execute(select(Manager).where(Manager.email == body.email.strip().lower()))
    ).scalar_one_or_none()
    if manager is None or not verify_password(body.password, manager.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_LOGIN_ERROR,
        )

    token, expires_in = issue_token(manager.id, manager.role, settings)
    return LoginResponse(
        accessToken=token,
        tokenType="Bearer",
        expiresIn=expires_in,
        manager=ManagerOut(
            id=manager.id,
            name=manager.name,
            email=manager.email,
            role=manager.role,
            locationIds=list(manager.location_ids or []),
        ),
    )
