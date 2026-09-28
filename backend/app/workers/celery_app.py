"""Celery application (spec §7.2: queues, waves, timeouts, retries).

Celery beat owns time: it ticks the scheduler (`run-due-jobs`, every 5 s,
for the memory backend and the status snapshot), runs the reconcile sweep
(`reconcile-stale-cases`, every 60 s) and the daily retention purge.
Orchestration runs in the worker process via `app.runtime` — the API process
only enqueues tasks (spec §7.5).
"""

from celery import Celery
from celery.schedules import crontab

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

celery_app.conf.beat_schedule = {
    "run-due-jobs": {
        "task": "app.workers.tasks.run_due_jobs",
        "schedule": 5.0,
    },
    "reconcile-stale-cases": {
        # Self-healing sweep (spec §9.1): re-enqueue deadline timers of
        # overdue cases that still expect action. Handlers re-check state,
        # so a repeated sweep is harmless.
        "task": "app.workers.tasks.reconcile_stale_cases",
        "schedule": 60.0,
    },
    "purge-old-messages": {
        "task": "app.workers.tasks.purge_old_messages",
        "schedule": crontab(hour=3, minute=0),  # daily, Europe/Madrid
    },
}

# Import side effect: connect the worker tracing bootstrap (worker_process_init
# / worker_process_shutdown). Every preforked child must install its own
# TracerProvider — a provider inherited across a fork is not usable.
import app.workers.tracing_bootstrap  # noqa: E402,F401


@celery_app.task(name="app.workers.celery_app.ping")
def ping() -> str:
    """Liveness task for worker smoke checks."""
    return "pong"
