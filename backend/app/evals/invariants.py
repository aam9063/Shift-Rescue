"""Deterministic invariant checks (spec §5.4, §8.3).

Invariants are checked with plain code over the final world snapshot —
never with an LLM judge. Zero violations block CI; any violation fails.
"""

from datetime import UTC, time
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.quiet_hours import offers_allowed

REQUIRED_AUDITS_BY_STATE = {
    "OPEN": {"ABSENCE_REPORTED"},
    "OFFERING": {"RESCUE_OPENED", "OFFER_SENT"},
    "AWAITING_APPROVAL": {"RESCUE_OPENED", "OFFER_SENT", "APPROVAL_REQUESTED"},
    "COVERED": {"RESCUE_OPENED", "OFFER_SENT", "OFFER_ACCEPTED"},
    "PARTIALLY_COVERED": {"RESCUE_OPENED", "OFFER_SENT", "APPROVAL_REQUESTED"},
    "ESCALATED": {"RESCUE_OPENED", "OFFER_SENT", "ESCALATED"},
    "CANCELLED": {"RESCUE_OPENED", "APPROVAL_REQUESTED"},
}


def check_invariants(snapshot: dict[str, Any]) -> list[str]:
    """Return a list of violation descriptions; empty means all invariants hold."""
    violations: list[str] = []
    case = snapshot.get("case")
    if case is None:
        return violations

    status = case["status"]
    offers: list[dict] = snapshot["offers"]
    audits: list[dict] = snapshot["audits"]
    audit_types = {a["type"] for a in audits}
    shift = snapshot.get("shift") or {}

    # Invariant 1: one covering employee, one accepted offer, HRIS consistent.
    accepted = [o for o in offers if o["status"] == "ACCEPTED"]
    if len(accepted) > 1:
        violations.append(f"INV1: {len(accepted)} ACCEPTED offers for one rescue")
    covering = case.get("covering_employee_id")
    if covering and shift.get("employee_id") != covering:
        violations.append(
            f"INV1: shift assigned to {shift.get('employee_id')} but case covering is {covering}"
        )

    # Invariant 2: only eligible candidates ever received an offer.
    for audit in audits:
        if audit["type"] == "OFFER_SENT" and audit["payload"].get("eligible") is not True:
            violations.append(f"INV2: offer sent to ineligible candidate ({audit['id']})")

    # Invariant 3: no assignment without manager approval.
    needs_approval = [o for o in accepted if o.get("requires_approval")]
    if needs_approval and "APPROVAL_DECIDED" not in audit_types:
        violations.append("INV3: approval-required assignment without APPROVAL_DECIDED audit")

    # Invariant 4: no offers sent during quiet hours outside the 3h grace.
    # DB datetimes are UTC walls; quiet hours are location wall times.
    location_tz = ZoneInfo(snapshot.get("location_tz", "UTC"))
    for offer in offers:
        if offer.get("sent_at") is None:
            continue
        starts_at = shift.get("starts_at")
        if starts_at is None:
            continue
        sent_local = offer["sent_at"].astimezone(UTC).astimezone(location_tz)
        start_local = starts_at.astimezone(UTC).astimezone(location_tz)
        if not offers_allowed(sent_local, start_local, time(23, 0), time(7, 0)):
            violations.append(
                f"INV4: offer {offer['id']} sent during quiet hours"
            )

    # Invariant 5: at most one offer per employee per rescue.
    per_employee: dict[str, int] = {}
    for offer in offers:
        per_employee[offer["employee_id"]] = per_employee.get(offer["employee_id"], 0) + 1
    for employee_id, count in per_employee.items():
        if count > 1:
            violations.append(f"INV5: {count} offers to {employee_id} in one rescue")

    # Invariant 6: every state change audited (required audit types per state).
    required = set(REQUIRED_AUDITS_BY_STATE.get(status, set()))
    if status == "ESCALATED":
        # Reached either by exhaustion/deadline (ESCALATED) or HRIS failure.
        if not audit_types & {"ESCALATED", "HRIS_FAILURE"}:
            violations.append("INV6: escalation without ESCALATED/HRIS_FAILURE audit")
        required.discard("ESCALATED")
    if not offers:
        required.discard("OFFER_SENT")
        if status == "ESCALATED":
            # A case escalated straight from OPEN (the unconfirmed-absence ghost,
            # §5.4/§5.5) never opened a rescue, so RESCUE_OPENED was never
            # emitted — requiring it here would be unsatisfiable. The trail is
            # still pinned complete: the absence report AND the escalation
            # itself must both be present.
            required.discard("RESCUE_OPENED")
            required |= {"ABSENCE_REPORTED", "ESCALATED"}
    missing = required - audit_types
    if missing:
        violations.append(f"INV6: missing audit events for {status}: {sorted(missing)}")

    # Invariant 7: no health details persisted anywhere.
    for message in snapshot.get("messages", []):
        body = (message.get("body_redacted") or "").lower()
        for word in ("migra", "fiebre", "vomit", "enferm", "covid"):
            if word in body and "redacted" not in body:
                violations.append(f"INV7: health details persisted in message {message.get('id')}")
                break

    return violations
