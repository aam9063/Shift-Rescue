"""Unit tests for the Celery app scaffold (no broker connection needed)."""

from app.core.config import get_settings
from app.workers.celery_app import celery_app


def test_celery_broker_comes_from_settings() -> None:
    assert celery_app.conf.broker_url == get_settings().redis_url
    assert celery_app.conf.result_backend == get_settings().redis_url


def test_ping_task_is_registered() -> None:
    assert "app.workers.celery_app.ping" in celery_app.tasks


def test_retention_purge_task_is_registered() -> None:
    # Celery loads this module through the app's include list (worker startup).
    import app.workers.tasks  # noqa: F401

    assert "app.workers.tasks" in celery_app.conf.include
    assert "app.workers.tasks.purge_old_messages" in celery_app.tasks
