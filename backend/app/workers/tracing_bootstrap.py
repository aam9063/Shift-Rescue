"""Worker-side tracing bootstrap: one TracerProvider per worker process.

The API lifespan installs the provider in the API process, but orchestration
and the LLM call now live in the Celery worker — without this bootstrap, real
interpretation calls produce no traces at all.

The provider must be installed per worker process: the prefork pool spawns
children after boot, and a `TracerProvider` inherited across a fork is not
usable — its `BatchSpanProcessor` owns a background exporter thread and locks
that do not survive a fork. Celery therefore dispatches `worker_process_init`
inside each child, and this module installs a fresh provider there.

Best effort by design: tracing disabled (no keys) is a no-op, and any failure
is logged and swallowed — a tracing problem must never stop a worker boot,
and a shutdown problem must never keep spans from being flushed elsewhere.
"""

from typing import Any

from celery.signals import worker_process_init, worker_process_shutdown
from structlog import get_logger

from app.core.config import get_settings
from app.observability.tracing import configure_tracing, shutdown_tracing

logger = get_logger(__name__)


@worker_process_init.connect
def _init_worker_tracing(**_kwargs: Any) -> None:
    """Install the TracerProvider in this preforked child (or solo worker)."""
    try:
        installed = configure_tracing(get_settings())
        logger.info("worker_tracing_bootstrap", installed=installed)
    except Exception as error:
        logger.warning("worker_tracing_bootstrap_failed", error=str(error)[:200])


@worker_process_shutdown.connect
def _flush_worker_tracing(**_kwargs: Any) -> None:
    """Flush buffered spans before the child exits; a lost batch is lost data."""
    try:
        shutdown_tracing()
    except Exception as error:
        logger.warning("worker_tracing_shutdown_failed", error=str(error)[:200])
