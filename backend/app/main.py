"""FastAPI application factory (spec §7.2)."""

import contextlib
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.status import router as status_router
from app.api.webhooks_twilio import router as twilio_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.observability.tracing import configure_tracing, shutdown_tracing


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_tracing(settings)
    # The API owns no scheduling: Celery beat ticks `run_due_jobs` every 5 s
    # and the worker runs the daily retention purge (spec §7.2/§7.3).
    structlog.get_logger(__name__).info(
        "scheduling_owned_by_worker",
        detail="Celery beat drives scheduled rescue work (run-due-jobs every 5s)",
    )
    try:
        yield
    finally:
        shutdown_tracing()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.service_name)

    app = FastAPI(title="Shift Rescue API", docs_url="/docs", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(twilio_router)
    app.include_router(status_router)
    return app
