"""Degraded-status endpoint (spec §9.3) consumed by the dashboard banner."""

from typing import Any

from fastapi import APIRouter, Depends

from app.observability.status import build_status, degraded_reasons

router = APIRouter(prefix="/api", tags=["status"])


def get_status_probe() -> Any:
    """Returns an object exposing `llm_configured`, `circuit_open`, `agent_paused`.

    Wired to the same runtime the webhooks use; overridable in tests.
    """
    from app.api.webhooks_twilio import get_twilio_service

    service = get_twilio_service()

    class _Probe:
        @property
        def llm_configured(self) -> bool:
            return getattr(service._orchestrator, "interpreter", None) is not None

        @property
        def circuit_open(self) -> bool:
            interpreter = getattr(service._orchestrator, "interpreter", None)
            llm = getattr(interpreter, "_llm", None)
            breaker = getattr(llm, "breaker", None)
            return bool(breaker and breaker.is_open())

        @property
        def agent_paused(self) -> bool:
            return getattr(service, "agent_paused", False)

    return _Probe()


@router.get("/status")
def system_status(probe: Any = Depends(get_status_probe)) -> dict[str, Any]:
    return build_status(
        degraded_reasons(
            llm_configured=probe.llm_configured,
            circuit_open=probe.circuit_open,
            agent_paused=probe.agent_paused,
        )
    )
