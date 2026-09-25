"""Celery tasks: inbound orchestration, scheduled ticks, retention purge."""

import json
from typing import TYPE_CHECKING, Any

import structlog
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.workers.async_runner import run_async
from app.workers.celery_app import celery_app

if TYPE_CHECKING:
    from app.runtime import RescueRuntime

logger = structlog.get_logger(__name__)

# Key and TTL for the runtime snapshot the worker publishes for the API
# status probe (spec §9.3); the API reads it, it never builds a runtime.
RUNTIME_SNAPSHOT_KEY = "shift_rescue:runtime_snapshot"
RUNTIME_SNAPSHOT_TTL_SECONDS = 30

# Transient failure classes worth a retry: DB/broker/network hiccups. The
# orchestrator already degrades on provider outages (§9.3), so those never
# surface here.
TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    OSError,  # connection reset, DNS, broker socket
    TimeoutError,
    SQLAlchemyError,  # dropped connection, deadlock, serialization failure
)


@celery_app.task(
    name="app.workers.tasks.process_inbound_message",
    bind=True,
    max_retries=3,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=False,
)
def process_inbound_message(self: Any, from_phone: str, message_sid: str, body: str) -> bool:
    """Handle one inbound message in the worker process (spec §7.4, §7.5).

    Idempotent by `message_sid`: the orchestrator rejects a duplicate
    `provider_message_id` (spec §7.4), so a redelivered task (acks_late) is a
    no-op — no second dedup mechanism lives here.
    """
    from app.runtime import get_worker_runtime

    handled = run_async(get_worker_runtime().handle_inbound(from_phone, message_sid, body))
    logger.info("worker_inbound_processed", message_sid=message_sid, recognized=handled)
    return handled


@celery_app.task(name="app.workers.tasks.apply_approval_decision")
def apply_approval_decision(approval_id: str, decision: str, decided_by: str) -> bool:
    """Apply a manager approval decision in the worker (spec §2.1, §7.5).

    The orchestrator owns the domain logic (state machine, offers, audit); the
    task only bridges Celery to it. Idempotent: `decide_approval` no-ops when
    the approval is not pending.
    """
    from app.runtime import get_worker_runtime

    run_async(
        get_worker_runtime().orchestrator.decide_approval(approval_id, decision, decided_by)
    )
    logger.info("worker_approval_applied", approval_id=approval_id, decision=decision)
    return True


@celery_app.task(name="app.workers.tasks.close_rescue")
def close_rescue_task(rescue_id: str, decided_by: str) -> bool:
    """Manual manager close in the worker (spec §7.5): same rule as approvals."""
    from app.runtime import get_worker_runtime

    run_async(get_worker_runtime().orchestrator.close_rescue(rescue_id, decided_by))
    logger.info("worker_rescue_closed", rescue_id=rescue_id)
    return True


@celery_app.task(name="app.workers.tasks.run_due_jobs")
def run_due_jobs() -> int:
    """Beat tick (spec §7.3): run due scheduled jobs, publish the snapshot."""
    from app.core.clock import SystemClock
    from app.runtime import get_worker_runtime

    runtime = get_worker_runtime()
    ran = run_async(runtime.scheduler.run_due(SystemClock().now()))
    if ran:
        logger.info("scheduler_ran_jobs", count=ran)
    publish_runtime_snapshot(runtime)
    return ran


def publish_runtime_snapshot(runtime: "RescueRuntime", client: Redis | None = None) -> None:
    """Publish the degraded-mode snapshot for the API probe (spec §9.3).

    Best effort: Redis unavailability is logged and swallowed — the scheduler
    tick must never fail because the probe cannot be refreshed.
    """
    snapshot = {
        "llm_configured": runtime.interpreter is not None,
        "circuit_open": runtime.circuit_open(),
        # Agent pause is per location and enforced per message by the
        # orchestrator; there is no global pause flag to report yet.
        "agent_paused": False,
    }
    try:
        client = client if client is not None else _redis_client()
        client.set(
            RUNTIME_SNAPSHOT_KEY,
            json.dumps(snapshot),
            ex=RUNTIME_SNAPSHOT_TTL_SECONDS,
        )
    except (RedisError, OSError) as error:
        logger.warning("runtime_snapshot_publish_failed", error=str(error)[:200])


def _redis_client() -> Redis:
    from app.core.config import get_settings

    return Redis.from_url(get_settings().redis_url)


@celery_app.task(name="app.workers.tasks.purge_old_messages")
def purge_old_messages_task() -> int:
    """Daily retention purge (spec §10): schedule it from Celery beat."""
    from app.observability.retention import _run_purge

    return _run_purge()
