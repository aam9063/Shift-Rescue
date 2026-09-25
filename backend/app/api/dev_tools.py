"""Demo-only dev tools (spec §7.5, decisions 1-3): drive the real pipeline.

The simulator never bypasses the domain: it resolves the employee and
enqueues the *same* Celery task the Twilio webhook enqueues, so idempotency,
dedup, conversation threading, LLM interpretation, auditing and delivery all
behave exactly as in production. The demo clock moves a shared Redis offset
that the worker's `DemoClock` reads, and immediately re-enqueues the
reconcile sweep so overdue cases escalate without waiting for the 60 s beat.

Double-gated (decision 2): `create_app` does not even register this router
outside `local`/`test`/`demo`, and `require_demo_environment` answers a hard
404 if the settings say otherwise at request time. Every route also requires
a manager JWT.
"""

from typing import cast
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    ManagerPrincipal,
    current_manager,
    get_db,
    require_demo_environment,
)
from app.core.clock import DEMO_CLOCK_OFFSET_KEY, DemoClock, redis_offset_source
from app.core.config import Settings, get_settings
from app.db.models import Employee
from app.schemas.dashboard import iso_utc
from app.workers.tasks import process_inbound_message, reconcile_stale_cases

router = APIRouter(
    prefix="/dev",
    tags=["dev-tools"],
    dependencies=[Depends(require_demo_environment)],
)

logger = structlog.get_logger(__name__)

# Sane bound for one demo advance: ±30 days in whole seconds.
MAX_DEMO_OFFSET_SECONDS = 30 * 24 * 3600

# The synthetic sid namespace: every simulated message stays distinguishable
# from a real Twilio one by its `provider_message_id` alone (acceptance 4).
SIM_SID_PREFIX = "sim_"


# --- request/response contracts (camelCase per the frontend wire shapes) -----


class SimulatorMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ClockAdvanceIn(BaseModel):
    seconds: int = Field(ge=-MAX_DEMO_OFFSET_SECONDS, le=MAX_DEMO_OFFSET_SECONDS)


class DemoClockOut(BaseModel):
    now: str  # ISO-8601 virtual time
    offsetSeconds: int


class DemoMutationOut(BaseModel):
    """Body of the 202 answers: enqueued, applied by the worker."""

    status: str  # "queued"
    id: str


def get_demo_redis(settings: Settings = Depends(get_settings)) -> Redis:
    """Redis client for the shared demo-clock offset (overridable in tests)."""
    return Redis.from_url(settings.redis_url)


@router.post(
    "/simulator/{employee_id}/messages",
    status_code=202,
    response_model=DemoMutationOut,
)
async def simulate_inbound_message(
    employee_id: str,
    body: SimulatorMessageIn,
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> DemoMutationOut:
    """Send a message as an employee through the real inbound pipeline.

    This is the same task the Twilio webhook enqueues
    (`app.api.webhooks_twilio.twilio_inbound` -> `process_inbound_message`):
    the worker's `RescueRuntime.handle_inbound` looks the employee up by
    phone and the orchestrator runs the full flow (interpretation, rescue
    opening, offers). The only difference from a real WhatsApp message is the
    synthetic `sim_<uuid>` provider sid.
    """
    employee = (
        await session.execute(select(Employee).where(Employee.id == employee_id))
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    message_sid = f"{SIM_SID_PREFIX}{uuid4()}"
    try:
        process_inbound_message.delay(employee.phone_e164, message_sid, body.text)
    except Exception as error:
        # A broker rejection must be loud: the caller retries, nothing is
        # silently dropped (same rule as the webhook).
        logger.error(
            "simulator_enqueue_failed",
            employee_id=employee_id,
            error=str(error)[:200],
        )
        raise HTTPException(status_code=500, detail="Could not enqueue the message") from None
    logger.info("simulator_message_enqueued", employee_id=employee_id, message_sid=message_sid)
    return DemoMutationOut(status="queued", id=message_sid)


@router.post("/clock/advance", response_model=DemoClockOut)
async def advance_demo_clock(
    body: ClockAdvanceIn,
    _principal: ManagerPrincipal = Depends(current_manager),
    client: Redis = Depends(get_demo_redis),
) -> DemoClockOut:
    """Move the shared demo-clock offset and sweep for overdue cases.

    The offset lives in Redis (`DEMO_CLOCK_OFFSET_KEY`), so the API and the
    worker agree on the new "now". The reconcile sweep runs right after the
    move so cases whose deadline has passed escalate immediately instead of
    waiting for the 60 s beat tick. Broker timers keep their real-time ETA —
    that limitation is the UI's and the runbook's to state, not this route's.
    """
    try:
        # Sync Redis client: `incrby` answers the new value directly.
        offset = cast(int, client.incrby(DEMO_CLOCK_OFFSET_KEY, body.seconds))
    except (RedisError, OSError) as error:
        logger.error("demo_clock_advance_failed", error=str(error)[:200])
        raise HTTPException(status_code=503, detail="Demo clock is unavailable") from None
    clock = DemoClock(redis_offset_source(client))
    # Sweep immediately (decision 3): overdue cases escalate now, not at the
    # next 60 s beat tick. A broker rejection must be loud, like the webhook's.
    reconcile_stale_cases.delay()
    logger.info("demo_clock_advanced", seconds=body.seconds, offset_seconds=offset)
    return DemoClockOut(now=iso_utc(clock.now()), offsetSeconds=offset)


@router.post("/clock/reset", response_model=DemoClockOut)
async def reset_demo_clock(
    _principal: ManagerPrincipal = Depends(current_manager),
    client: Redis = Depends(get_demo_redis),
) -> DemoClockOut:
    """Zero the shared demo-clock offset and sweep for overdue cases.

    A leftover offset silently moves "now" for the whole worker (today's
    shifts read as already finished and the agent answers "out of scope"), so
    undoing an advance is a real backend operation, not a client trick: the
    offset is set back to zero in Redis and the reconcile sweep runs
    immediately, exactly as after an advance.
    """
    try:
        client.set(DEMO_CLOCK_OFFSET_KEY, "0")
    except (RedisError, OSError) as error:
        logger.error("demo_clock_reset_failed", error=str(error)[:200])
        raise HTTPException(status_code=503, detail="Demo clock is unavailable") from None
    clock = DemoClock(redis_offset_source(client))
    # Sweep immediately: cases whose deadline moved back with the clock stop
    # escalating on stale evidence, same rule as the advance route.
    reconcile_stale_cases.delay()
    logger.info("demo_clock_reset")
    return DemoClockOut(now=iso_utc(clock.now()), offsetSeconds=clock.offset_seconds())


@router.get("/clock", response_model=DemoClockOut)
async def get_demo_clock(
    _principal: ManagerPrincipal = Depends(current_manager),
    client: Redis = Depends(get_demo_redis),
) -> DemoClockOut:
    """Current virtual time and offset (the Simulator screen shows both).

    A Redis failure degrades to offset zero (real time) with a warning —
    the same contract as the worker's `DemoClock`.
    """
    clock = DemoClock(redis_offset_source(client))
    return DemoClockOut(now=iso_utc(clock.now()), offsetSeconds=clock.offset_seconds())
