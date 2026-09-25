"""Degraded status surface (spec §9.3)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.status import get_status_probe, router
from app.observability.status import (
    AGENT_PAUSED,
    LLM_CIRCUIT_OPEN,
    LLM_NOT_CONFIGURED,
    build_status,
    degraded_reasons,
)


class Probe:
    def __init__(self, llm_configured=True, circuit_open=False, agent_paused=False):
        self.llm_configured = llm_configured
        self.circuit_open = circuit_open
        self.agent_paused = agent_paused


def test_healthy_system_reports_not_degraded() -> None:
    assert degraded_reasons(llm_configured=True, circuit_open=False, agent_paused=False) == []


def test_open_circuit_marks_degraded() -> None:
    reasons = degraded_reasons(llm_configured=True, circuit_open=True, agent_paused=False)
    assert reasons == [LLM_CIRCUIT_OPEN]


def test_missing_interpreter_marks_degraded_without_circuit_noise() -> None:
    reasons = degraded_reasons(llm_configured=False, circuit_open=True, agent_paused=False)
    assert reasons == [LLM_NOT_CONFIGURED]


def test_paused_agent_marks_degraded() -> None:
    reasons = degraded_reasons(llm_configured=False, circuit_open=False, agent_paused=True)
    assert reasons == [LLM_NOT_CONFIGURED, AGENT_PAUSED]


def test_build_status_includes_details() -> None:
    status = build_status([AGENT_PAUSED])
    assert status["degraded"] is True
    assert status["reasons"] == [AGENT_PAUSED]
    assert status["details"] and "pausa" in status["details"][0]


def test_endpoint_reports_degraded_reasons(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_status_probe] = lambda: Probe(circuit_open=True)

    with TestClient(app) as client:
        body = client.get("/api/status").json()

    assert body["degraded"] is True
    assert body["reasons"] == [LLM_CIRCUIT_OPEN]
