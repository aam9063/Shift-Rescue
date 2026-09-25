"""Celery task modules (populated by rescue-orchestration)."""

from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.purge_old_messages")
def purge_old_messages_task() -> int:
    """Daily retention purge (spec §10): schedule it from Celery beat."""
    from app.observability.retention import _run_purge

    return _run_purge()
