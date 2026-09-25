"""Shared worker runtime (spec §7.2): one construction path, one owner.

The Celery worker process builds the rescue runtime exactly once (memoized):
DB sessions, Twilio channel, simulated scheduler, workforce adapter and the
orchestrator with its interpreter (ADR-004). The API process never builds any
of this — its webhooks only validate the request and enqueue tasks (§7.5).
"""

from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.factory import build_interpreter, describe_provider
from app.agent.interpreter import MessageInterpreter
from app.channels.twilio_whatsapp import TwilioWhatsAppChannel
from app.core.clock import SystemClock
from app.core.config import Settings, get_settings
from app.db.session import create_engine_and_session
from app.integrations.workforce.mock import MockWorkforceAdapter
from app.services.orchestrator import RescueOrchestrator
from app.workers.celery_scheduler import CeleryScheduler
from app.workers.scheduler import SimScheduler

logger = structlog.get_logger(__name__)

# Timer backends (spec §7.3): the broker owns production timers; the in-memory
# scheduler remains for single-process local runs, tests and the eval harness.
Scheduler = SimScheduler | CeleryScheduler


@dataclass(frozen=True)
class RescueRuntime:
    """Everything the worker needs to run rescue flows."""

    session_factory: async_sessionmaker[AsyncSession]
    channel: TwilioWhatsAppChannel
    workforce: MockWorkforceAdapter
    clock: SystemClock
    scheduler: Scheduler
    orchestrator: RescueOrchestrator
    interpreter: MessageInterpreter | None

    def circuit_open(self) -> bool:
        """Whether the interpreter's circuit breaker is currently open.

        Same-process introspection only: the API never calls this — it reads
        the snapshot the worker publishes to Redis (spec §9.3).
        """
        if self.interpreter is None:
            return False
        llm = getattr(self.interpreter, "_llm", None)
        breaker = getattr(llm, "breaker", None)
        return bool(breaker and breaker.is_open())

    async def handle_inbound(self, from_phone: str, message_sid: str, body: str) -> bool:
        """Map the sender to an employee and hand the message to the orchestrator.

        Unknown senders are ignored. A duplicate `message_sid` is a harmless
        no-op: the orchestrator deduplicates by `provider_message_id` (§7.4) —
        never add a second mechanism here.
        """
        from app.db.models import Employee

        async with self.session_factory() as session:
            employee = (
                await session.execute(select(Employee).where(Employee.phone_e164 == from_phone))
            ).scalar_one_or_none()
        if employee is None:
            return False

        await self.orchestrator.handle_inbound(
            conversation_id=f"conv_twilio_{from_phone}",
            employee_id=employee.id,
            provider_message_id=message_sid,
            text=body,
        )
        return True


def build_runtime(settings: Settings, *, scheduler: Scheduler | None = None) -> RescueRuntime:
    """Construct the full rescue runtime exactly as the API service did.

    The scheduler backend is injectable so tests and the eval harness keep
    full control (`ShiftRescueTarget` builds `RescueRuntime` with a
    `SimScheduler`); otherwise `settings.scheduler_backend` picks it: the
    broker-backed `CeleryScheduler` in production, `SimScheduler` for the
    single-process `memory` backend.
    """
    # Pass the database URL explicitly: falling back to the ambient settings
    # would make the runtime silently ignore the settings it was given (and
    # connect to a developer's local database from tests).
    # The engine lives in the pool held by the session factory.
    _, session_factory = create_engine_and_session(settings.database_url)
    channel = TwilioWhatsAppChannel(
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        from_number=settings.twilio_whatsapp_from,
    )
    clock = SystemClock()
    if scheduler is None:
        backend = settings.scheduler_backend
        if backend == "celery":
            scheduler = CeleryScheduler(clock)
        elif backend == "memory":
            scheduler = SimScheduler()
        else:
            raise ValueError(
                f"Unknown scheduler_backend '{backend}' (expected 'celery' or 'memory')"
            )
    workforce = MockWorkforceAdapter(session_factory)
    interpreter = build_interpreter(settings)
    orchestrator = RescueOrchestrator(
        session_factory=session_factory,
        workforce=workforce,
        channel=channel,
        scheduler=scheduler,
        clock=clock,
        interpreter=interpreter,
    )
    for name, handler in orchestrator.task_handlers().items():
        scheduler.register(name, handler)
    logger.info(
        "llm_path",
        active=interpreter is not None,
        detail=describe_provider(settings),
    )
    return RescueRuntime(
        session_factory=session_factory,
        channel=channel,
        workforce=workforce,
        clock=clock,
        scheduler=scheduler,
        orchestrator=orchestrator,
        interpreter=interpreter,
    )


_RUNTIME: RescueRuntime | None = None


def get_worker_runtime() -> RescueRuntime:
    """Memoized runtime for the worker process (one construction per process)."""
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = build_runtime(get_settings())
    return _RUNTIME


def reset_worker_runtime() -> None:
    """Force the next `get_worker_runtime()` to rebuild (tests and reloads)."""
    global _RUNTIME
    _RUNTIME = None
