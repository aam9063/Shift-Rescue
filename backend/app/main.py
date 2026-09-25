"""FastAPI application factory (spec §7.2)."""

import contextlib
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.approvals import router as approvals_router
from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.dev_tools import router as dev_tools_router
from app.api.employees import router as employees_router
from app.api.health import router as health_router
from app.api.interpretations import router as interpretations_router
from app.api.locations import router as locations_router
from app.api.metrics import router as metrics_router
from app.api.rescues import router as rescues_router
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
    # Dashboard SPA origins (spec §7.5): exactly the configured list, never a
    # wildcard — credentials ride on the Authorization header.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health_router)
    app.include_router(twilio_router)
    app.include_router(status_router)
    app.include_router(auth_router)
    app.include_router(locations_router)
    app.include_router(rescues_router)
    app.include_router(approvals_router)
    app.include_router(conversations_router)
    app.include_router(interpretations_router)
    app.include_router(employees_router)
    # Demo-only dev routes (spec §7.5, decision 2): not even advertised —
    # the router is registered only in demo environments, and the routes
    # still answer a hard 404 if the environment changes under them.
    if settings.demo_clock_enabled:
        app.include_router(dev_tools_router)
    app.include_router(metrics_router)
    return app
