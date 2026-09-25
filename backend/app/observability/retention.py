"""Retention purge (spec §10).

Message bodies have a configurable retention window (30 days by default in the
demo). Purging removes the messages — which is where the content lives — while
the audit trail, cases and offers (metadata only) stay.
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message

DEFAULT_RETENTION_DAYS = 30


async def purge_old_messages(
    session: AsyncSession,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now: datetime,
) -> int:
    """Delete messages older than the retention window. Returns rows removed."""
    if retention_days <= 0:
        return 0  # retention disabled

    cutoff = now - timedelta(days=retention_days)
    aged = (
        await session.execute(select(Message.id, Message.created_at))
    ).all()
    to_delete = [message_id for message_id, created_at in aged if _is_older(created_at, cutoff)]
    if not to_delete:
        return 0

    await session.execute(delete(Message).where(Message.id.in_(to_delete)))
    await session.commit()
    return len(to_delete)


def _is_older(created_at: datetime, cutoff: datetime) -> bool:
    """SQLite returns naive datetimes; treat them as UTC (see orchestrator)."""
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=cutoff.tzinfo)
    return created_at < cutoff


def _run_purge() -> int:
    """Blocking entry point for Celery and for `python -m app.observability.retention`."""
    import asyncio

    from app.core.clock import SystemClock
    from app.core.config import get_settings
    from app.db.session import create_engine_and_session

    async def _purge() -> int:
        settings = get_settings()
        engine, session_factory = create_engine_and_session()
        async with session_factory() as session:
            removed = await purge_old_messages(
                session,
                retention_days=settings.message_retention_days,
                now=SystemClock().now(),
            )
        await engine.dispose()
        return removed

    return asyncio.run(_purge())


if __name__ == "__main__":
    print(f"Purged {_run_purge()} message(s).")
