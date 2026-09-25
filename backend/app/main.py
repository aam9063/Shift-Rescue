"""FastAPI application factory (spec §7.2)."""

import asyncio
import contextlib
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.status import router as status_router
from app.api.webhooks_twilio import router as twilio_router
from app.core.config import get_settings
from app.core.logging import configure_logging

SCHEDULER_TICK_SECONDS = 5


async def _scheduler_ticker() -> None:
    """Drives scheduled rescue work (wave timeouts, deadlines, approvals).

    The Celery beat schedule takes over in production; until then the API
    process ticks the in-memory scheduler so timeouts actually fire.
    """
    from app.api.webhooks_twilio import get_twilio_service
    from app.core.clock import SystemClock

    logger = structlog.get_logger(__name__)
    while True:
        await asyncio.sleep(SCHEDULER_TICK_SECONDS)
        try:
            service = get_twilio_service()
            scheduler = getattr(service, "scheduler", None)
            if scheduler is None:
                continue
            ran = await scheduler.run_due(SystemClock().now())
            if ran:
                logger.info("scheduler_ran_jobs", count=ran)
        except Exception as error:  # never let the ticker die
            logger.warning("scheduler_tick_failed", error=str(error)[:200])


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    ticker = asyncio.create_task(_scheduler_ticker())
    try:
        yield
    finally:
        ticker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ticker


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.service_name)

    app = FastAPI(title="Shift Rescue API", docs_url="/docs", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(twilio_router)
    app.include_router(status_router)
    return app
