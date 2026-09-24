"""Scenario runner (spec §8.2-§8.3): YAML scenarios against ShiftRescueTarget."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from app.evals.invariants import check_invariants
from app.evals.target import ShiftRescueTarget


async def run_scenario(spec: dict[str, Any]) -> dict[str, Any]:
    """Execute one YAML scenario and evaluate expectations + invariants."""
    absence = spec["absence"]
    personas: dict[str, list[dict]] = spec.get("personas", {})
    expect: dict[str, Any] = spec.get("expect", {})

    now = datetime.fromisoformat(spec["now"])
    location_tz = spec.get("timezone", "UTC")
    target = await ShiftRescueTarget.create(
        floor_count=spec.get("floor_count", 4),
        now=now,
        shift_starts_in=timedelta(minutes=spec.get("shift_starts_in_minutes", 20)),
        hris_fail_assignments=spec.get("hris_fail_assignments", 0),
        llm_down=spec.get("llm_down", False),
        timezone=location_tz,
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

    # 2b. Manager decisions on pending approvals.
    for decision in spec.get("manager", []):
        delta = float(decision["after_minutes"]) - previous
        if delta > 0:
            await target.advance_clock(delta)
        previous = max(previous, float(decision["after_minutes"]))
        approval_id = await target.latest_pending_approval()
        if approval_id is not None:
            await target.orchestrator.decide_approval(
                approval_id, decision["decision"], "mgr_1"
            )

    # 3. Let every scheduled job (waves, deadlines, timeouts) fire.
    horizon = max(60.0, steps[-1][0] + 1 if steps else 0.0)
    for decision in spec.get("manager", []):
        horizon = max(horizon, float(decision["after_minutes"]) + 1)
    await target.advance_clock(max(0.0, horizon - previous))

    snapshot = await target.snapshot()
    snapshot["location_tz"] = location_tz
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
