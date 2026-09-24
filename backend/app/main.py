"""FastAPI application factory (spec §7.2)."""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.webhooks_twilio import router as twilio_router
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.service_name)

    app = FastAPI(title="Shift Rescue API", docs_url="/docs")
    app.include_router(health_router)
    app.include_router(twilio_router)
    return app
