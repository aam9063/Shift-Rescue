"""Celery application (spec §7.2: queues, waves, timeouts, retries).

Foundation only registers a ping task; orchestration tasks arrive with
`rescue-orchestration`.
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "shift_rescue",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Madrid",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="app.workers.celery_app.ping")
def ping() -> str:
    """Liveness task for worker smoke checks."""
    return "pong"
