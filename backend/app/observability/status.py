"""Degraded-mode status surface (spec §9.3).

Pure composition of the reasons the agent is running degraded, so the
dashboard can show one banner instead of the operator guessing:

* the LLM is not configured at all (parser-only mode),
* the LLM circuit breaker is open (provider failing),
* the agent is paused for the location.
"""

from typing import Any

LLM_NOT_CONFIGURED = "llm_not_configured"
LLM_CIRCUIT_OPEN = "llm_circuit_open"
AGENT_PAUSED = "agent_paused"

DESCRIPTIONS: dict[str, str] = {
    LLM_NOT_CONFIGURED: "El intérprete LLM no está configurado: se usa el parser determinista.",
    LLM_CIRCUIT_OPEN: "El proveedor del LLM está fallando: modo degradado con parser determinista.",
    AGENT_PAUSED: "El agente está en pausa en este local: los mensajes van al manager.",
}


def degraded_reasons(
    *,
    llm_configured: bool,
    circuit_open: bool,
    agent_paused: bool,
) -> list[str]:
    reasons: list[str] = []
    if not llm_configured:
        reasons.append(LLM_NOT_CONFIGURED)
    elif circuit_open:
        # With no interpreter at all the breaker is irrelevant.
        reasons.append(LLM_CIRCUIT_OPEN)
    if agent_paused:
        reasons.append(AGENT_PAUSED)
    return reasons


def build_status(reasons: list[str]) -> dict[str, Any]:
    return {
        "degraded": bool(reasons),
        "reasons": reasons,
        "details": [DESCRIPTIONS.get(reason, reason) for reason in reasons],
    }
