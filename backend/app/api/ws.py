"""Live event channel for the dashboard (spec §7.5): a thin authenticated relay.

`WS /ws/locations/{location_id}?token=...` validates the manager's JWT before
the socket streams anything, checks the manager's right to that location, and
then forwards every event published on the location's Redis channel as JSON
text. It is a relay only: no database access per event, no business logic —
the screens keep rendering from the API, the events just tell them what to
refetch (spec §7.6).

Close codes (sent right after `accept` so the browser can actually read them:
closing before the accept degenerates into an opaque HTTP 403 handshake
rejection under uvicorn, which would hide the reason from the client):

- 4401: missing, malformed, expired or wrong-role token
- 4403: a manager without rights on that location
- 4503: the event broker (Redis) is unavailable
"""

import asyncio
import contextlib

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.models import Manager
from app.db.session import create_engine_and_session
from app.events import EventSubscription, channel_for, subscribe
from app.security.tokens import verify_token

router = APIRouter()

logger = structlog.get_logger(__name__)

ALLOWED_ROLES = ("manager", "operator")


def ws_session_factory(
    settings: Settings = Depends(get_settings),
) -> async_sessionmaker[AsyncSession]:
    """One short-lived session factory per socket (the manager check is the
    only DB access in the whole connection — never per event)."""
    _, factory = create_engine_and_session(settings.database_url)
    return factory


async def _reject(websocket: WebSocket, code: int) -> None:
    """Answer the handshake with a close code the client can read."""
    await websocket.accept()
    await websocket.close(code=code)


async def _forward(websocket: WebSocket, subscription: EventSubscription) -> None:
    """Relay loop: publish-side frames in, socket text frames out."""
    async for event in subscription.events():
        await websocket.send_text(event.to_json())


async def _drain(websocket: WebSocket) -> None:
    """Consume client frames until the socket closes.

    The relay and this loop run together and the connection ends when EITHER
    finishes. Awaiting `websocket.receive()` alone deadlocks against a client
    that is waiting for the server to finish (the browser and the test client
    both do), which is how this hung the suite the first time.
    """
    try:
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        return


@router.websocket("/ws/locations/{location_id}")
async def location_events(
    websocket: WebSocket,
    location_id: str,
    token: str = "",
    session_factory: async_sessionmaker[AsyncSession] = Depends(ws_session_factory),
    settings: Settings = Depends(get_settings),
) -> None:
    """Stream one location's dashboard events to an authenticated manager."""
    claims = verify_token(token, settings) if token else None
    if claims is None or claims.role not in ALLOWED_ROLES:
        await _reject(websocket, 4401)
        return

    # The manager may only watch their own locations; the operator role sees
    # everything (spec §7.6). Seeded managers carry `location_ids`.
    async with session_factory() as session:
        manager = (
            await session.execute(select(Manager).where(Manager.id == claims.manager_id))
        ).scalar_one_or_none()
    if manager is None or (
        claims.role == "manager" and location_id not in (manager.location_ids or [])
    ):
        await _reject(websocket, 4403)
        return

    try:
        # Subscribe BEFORE accepting: a down broker must answer a clear close
        # code instead of a socket that hangs open and never forwards (§9.3).
        subscription = await subscribe(settings.redis_url, channel_for(location_id))
    except Exception as error:
        logger.warning(
            "ws_event_broker_unavailable",
            location_id=location_id,
            error=str(error)[:200],
        )
        await _reject(websocket, 4503)
        return

    await websocket.accept()
    relay = asyncio.create_task(_forward(websocket, subscription))
    listener = asyncio.create_task(_drain(websocket))
    try:
        # Whichever ends first ends the connection: the client going away, the
        # subscription finishing (the broker closed), or a socket error.
        await asyncio.wait({relay, listener}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        # Close BEFORE cancelling: cancelling a `receive()` that is blocked in
        # the ASGI portal deadlocks the test client, while closing the socket
        # lets the listener raise its disconnect and finish on its own.
        with contextlib.suppress(RuntimeError):
            await websocket.close()
        relay.cancel()
        await asyncio.gather(relay, listener, return_exceptions=True)
        await subscription.close()


__all__ = ["router", "ws_session_factory"]
