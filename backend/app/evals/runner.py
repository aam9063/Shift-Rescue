"""Scenario runner (spec §8.2-§8.3): YAML scenarios against ShiftRescueTarget."""

import uuid
from datetime import datetime
from typing import Any

from app.evals.invariants import check_invariants
from app.evals.target import ShiftRescueTarget


async def run_scenario(spec: dict[str, Any]) -> dict[str, Any]:
    """Execute one YAML scenario and evaluate expectations + invariants."""
    absence = spec["absence"]
    personas: dict[str, list[dict]] = spec.get("personas", {})
    expect: dict[str, Any] = spec.get("expect", {})

    now = datetime.fromisoformat(spec["now"])
    target = await ShiftRescueTarget.create(
        floor_count=spec.get("floor_count", 4), now=now
    )

    # 1. The absence is reported.
    await target.inject_employee_message(
        employee_id=absence["employee"],
        text=absence["message"],
        conversation_id="conv_1",
        provider_message_id=f"prov_report_{uuid.uuid4().hex[:8]}",
    )

    # 1b. The standard flow: the absent employee explicitly confirms (spec §2.1).
    if absence.get("confirm", True):
        await target.advance_clock(0.5)
        await target.inject_employee_message(
            employee_id=absence["employee"],
            text="sí",
            conversation_id="conv_1",
            provider_message_id=f"prov_confirm_{uuid.uuid4().hex[:8]}",
        )

    # 2. Personas respond on their own schedule (deterministic scripts).
    steps: list[tuple[float, str, str]] = []
    for employee_id, script in personas.items():
        for step in script:
            steps.append((float(step["after_minutes"]), employee_id, step["text"]))
    steps.sort(key=lambda s: s[0])

    previous = 0.0
    for after_minutes, employee_id, text in steps:
        delta = after_minutes - previous
        if delta > 0:
            await target.advance_clock(delta)
        previous = after_minutes
        await target.inject_employee_message(
            employee_id=employee_id,
            text=text,
            conversation_id=f"conv_{employee_id}",
            provider_message_id=f"prov_{uuid.uuid4().hex[:8]}",
        )

    # 3. Let every scheduled job (waves, deadlines, timeouts) fire.
    if steps:
        await target.advance_clock(max(0.0, 60.0 - steps[-1][0]))

    snapshot = await target.snapshot()
    violations = check_invariants(snapshot)

    case = snapshot.get("case") or {}
    covering = case.get("covering_employee_id")
    passed = True
    expectation_failures: list[str] = []

    expected_state = expect.get("final_state")
    if expected_state and case.get("status") != expected_state:
        passed = False
        expectation_failures.append(
            f"final_state: expected {expected_state}, got {case.get('status')}"
        )

    expected_covering = expect.get("covering_employee_in")
    if expected_covering and covering not in expected_covering:
        passed = False
        expectation_failures.append(
            f"covering: expected one of {expected_covering}, got {covering}"
        )

    for template_key in expect.get("templates_sent", []):
        if not target.channel.with_template(template_key):
            passed = False
            expectation_failures.append(f"missing template: {template_key}")

    if expect.get("invariants") == "all" and violations:
        passed = False
        expectation_failures.append(f"invariant violations: {violations}")

    return {
        "scenario": spec["id"],
        "description": spec.get("description", ""),
        "final_state": case.get("status"),
        "covering_employee_id": covering,
        "expectations_passed": passed,
        "expectation_failures": expectation_failures,
        "invariant_violations": violations,
        "offers": snapshot["offers"],
        "channel_messages": len(snapshot["channel_sent"]),
        "simulated_minutes": 60.0 + (steps[-1][0] if steps else 0.0),
    }
