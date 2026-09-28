"""End-to-end check of the configured LLM provider (ADR-004).

Sends a few representative Spanish WhatsApp messages through the real
`build_interpreter()` path — the same object the API injects — and prints the
interpreted intent, confidence, model, tokens, latency and cost per message.
Prints no credential.

    cd backend && uv run python ../scripts/verify_llm.py

Exit codes: 0 provider answers, 2 provider not configured, 1 call failed.
"""

import asyncio
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.agent.factory import build_interpreter, describe_provider  # noqa: E402
from app.core.config import Settings  # noqa: E402

MESSAGES = [
    "buenas, me encuentro fatal, hoy no puedo ir a currar",
    "no puedo, lo siento",
    "sí, puedo cubrirlo pero llego a las 15:15",
]


async def main() -> int:
    settings = Settings()
    interpreter = build_interpreter(settings)
    if interpreter is None:
        print("NOT CONFIGURED: set LLM_PROVIDER and the provider key in backend/.env")
        return 2

    print(f"provider: {describe_provider(settings)}")
    print(f"threshold: {interpreter.confidence_threshold}")
    client = getattr(interpreter, "_llm", None)

    failures = 0
    for message in MESSAGES:
        started = time.perf_counter()
        result = await interpreter.interpret(
            message, {"rescue_id": "wiring-check-001", "shifts_48h": "2"}
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(client, "last_usage", None) or {}
        print(
            f"  [{result.intent:<18}] confidence={result.confidence:.2f} "
            f"latency={elapsed_ms}ms model={usage.get('model', '?')} "
            f"tokens={int(usage.get('input_tokens', 0))}/{int(usage.get('output_tokens', 0))} "
            f"cost=${usage.get('cost_usd', 0):.6f}"
        )
        print(f"      message: {message!r}")
        if result.intent == "UNCLEAR" and result.confidence == 0.0:
            failures += 1

    if failures == len(MESSAGES):
        print("FAILED: every message degraded to the fallback (check provider logs)")
        return 1

    print("OK: the configured provider answers with structured interpretations")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
