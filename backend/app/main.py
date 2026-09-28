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
from app.api.evals import router as evals_router
from app.api.health import router as health_router
from app.api.interpretations import router as interpretations_router
from app.api.locations import router as locations_router
from app.api.metrics import router as metrics_router
from app.api.rescues import router as rescues_router
from app.api.shifts import router as shifts_router
from app.api.status import router as status_router
from app.api.webhooks_twilio import router as twilio_router
from app.api.ws import router as ws_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.observability.tracing import configure_tracing, shutdown_tracing


def _init_sentry(settings: Settings) -> None:
    """Best-effort Sentry init (spec §9.3 spirit): never stops the boot.

    Unset DSN is a silent no-op (the setting exists for `.env` parity). A
    failure is logged and swallowed; the DSN itself is never logged. Twin
    copy lives in `app/workers/tracing_bootstrap.py` (worker process).
    """
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=0.1,
        )
        structlog.get_logger(__name__).info("sentry_initialized")
    except Exception as error:
        structlog.get_logger(__name__).warning(
            "sentry_init_failed", error=str(error)[:200]
        )


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_tracing(settings)
    _init_sentry(settings)
    # The API owns no scheduling: Celery beat runs the reconcile sweep and the
    # daily retention purge; timers themselves are broker-owned (spec §7.2/§7.3).
    structlog.get_logger(__name__).info(
        "scheduling_owned_by_worker",
        detail="Celery beat drives the reconcile sweep and the retention purge",
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
    app.include_router(ws_router)
    app.include_router(twilio_router)
    app.include_router(status_router)
    app.include_router(auth_router)
    app.include_router(locations_router)
    app.include_router(shifts_router)
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
    app.include_router(evals_router)
    return app
