"""Degraded-status endpoint (spec §9.3) consumed by the dashboard banner.

The probe reads only its own configuration plus the snapshot the worker
publishes to Redis — no private access into another process's objects.
"""

import json
from typing import Any, cast

import structlog
from fastapi import APIRouter, Depends
from redis import Redis
from redis.exceptions import RedisError

from app.agent.factory import is_provider_configured
from app.core.config import Settings, get_settings
from app.observability.status import build_status, degraded_reasons
from app.workers.tasks import RUNTIME_SNAPSHOT_KEY

router = APIRouter(prefix="/api", tags=["status"])

logger = structlog.get_logger(__name__)


class StatusProbe:
    """Read-only degraded-mode probe: configuration plus the worker snapshot."""

    def __init__(self, settings: Settings, snapshot: dict[str, bool]) -> None:
        self._settings = settings
        self._snapshot = snapshot

    @property
    def llm_configured(self) -> bool:
        return is_provider_configured(self._settings)

    @property
    def circuit_open(self) -> bool:
        return bool(self._snapshot.get("circuit_open", False))

    @property
    def agent_paused(self) -> bool:
        return bool(self._snapshot.get("agent_paused", False))


def read_runtime_snapshot(client: Redis | None = None) -> dict[str, bool]:
    """Read the worker-published snapshot; absent or unreadable means no
    degradation observed (closed breaker), matching today's semantics (§9.3)."""
    try:
        client = client if client is not None else _redis_client()
        raw = cast("str | bytes | bytearray | None", client.get(RUNTIME_SNAPSHOT_KEY))
    except (RedisError, OSError) as error:
        logger.warning("runtime_snapshot_read_failed", error=str(error)[:200])
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("runtime_snapshot_unreadable")
        return {}
    if not isinstance(data, dict):
        logger.warning("runtime_snapshot_unreadable")
        return {}
    return {key: bool(value) for key, value in data.items() if isinstance(key, str)}


def _redis_client() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_status_probe() -> StatusProbe:
    """Probe built from configuration plus the Redis snapshot (overridable)."""
    return StatusProbe(get_settings(), read_runtime_snapshot())


@router.get("/status")
def system_status(probe: StatusProbe = Depends(get_status_probe)) -> dict[str, Any]:
    return build_status(
        degraded_reasons(
            llm_configured=probe.llm_configured,
            circuit_open=probe.circuit_open,
            agent_paused=probe.agent_paused,
        )
    )
