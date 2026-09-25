"""Dashboard endpoint tests: every endpoint against the seeded SQLite world.

Covers reads, the settings PATCH, enqueue-backed writes (202, failure -> 500),
filters and the redaction/health rules (spec §10): health details and
unredacted bodies never appear in any response.
"""

from datetime import timedelta

import pytest

from app.workers.tasks import apply_approval_decision as approval_task
from app.workers.tasks import close_rescue_task
from tests.conftest import (
    APPROVAL_ID,
    CONVERSATION_ID,
    INTERPRETATION_ID,
    LOCATION_ID,
    MANAGER_ID,
    NOW,
    OPERATOR_ID,
    RESCUE_ID,
    auth_headers,
)

SHIFT_START = (NOW + timedelta(hours=2)).strftime("%H:%M")
SHIFT_END = (NOW + timedelta(hours=10)).strftime("%H:%M")
METRICS_DAY = NOW.date().isoformat()


class StubTask:
    """Records `.delay` calls; raises when armed (enqueue failure path)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.error: Exception | None = None

    def delay(self, *args) -> None:
        if self.error is not None:
            raise self.error
        self.calls.append(args)


@pytest.fixture()
def stub_approval(monkeypatch):
    stub = StubTask()
    monkeypatch.setattr(approval_task, "delay", stub.delay)
    return stub


@pytest.fixture()
def stub_close(monkeypatch):
    stub = StubTask()
    monkeypatch.setattr(close_rescue_task, "delay", stub.delay)
    return stub


async def assert_no_health_leak(response) -> None:
    """Health details (spec §10) never appear in any response body."""
    text = response.text
    assert "environment" not in text
    assert text != "local"  # the default app_env never leaks verbatim
    assert "migra" not in text  # unredacted health word from the world


async def test_locations_list(client) -> None:
    response = await client.get("/api/locations", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert [loc["id"] for loc in body] == [LOCATION_ID]
    assert body[0]["name"] == "Test Bar"
    assert body[0]["timezone"] == "UTC"
    await assert_no_health_leak(response)


async def test_shifts_list_and_filters(client) -> None:
    response = await client.get(
        f"/api/locations/{LOCATION_ID}/shifts", headers=auth_headers()
    )
    assert response.status_code == 200
    shifts = response.json()
    assert len(shifts) == 1
    shift = shifts[0]
    assert shift["id"] == "shift_1"
    assert shift["locationId"] == LOCATION_ID
    assert shift["role"] == "floor"
    assert shift["assigneeName"] == "Ana Floor"
    assert shift["status"] == "absent"
    assert shift["startsAt"].endswith("+00:00")

    # from/to window that excludes the shift.
    empty = await client.get(
        f"/api/locations/{LOCATION_ID}/shifts",
        params={"from": "2027-01-01T00:00:00Z", "to": "2027-01-02T00:00:00Z"},
        headers=auth_headers(),
    )
    assert empty.status_code == 200
    assert empty.json() == []


async def test_unknown_location_404(client) -> None:
    response = await client.get("/api/locations/loc_missing/shifts", headers=auth_headers())
    assert response.status_code == 404


async def test_get_settings(client) -> None:
    response = await client.get(
        f"/api/locations/{LOCATION_ID}/settings", headers=auth_headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agentPaused"] is False
    assert body["waveSize"] == 3
    assert body["waveIntervalMinutes"] == 10
    assert body["quietStart"] == "23:00"
    assert body["quietEnd"] == "07:00"
    assert [w["label"] for w in body["rankingWeights"]] == [
        "Coverage equity",
        "Proximity (same zone)",
        "Extra-shift preference",
        "No overtime first",
    ]


async def test_patch_settings(client) -> None:
    response = await client.patch(
        f"/api/locations/{LOCATION_ID}/settings",
        json={
            "agentPaused": True,
            "waveSize": 5,
            "rankingWeights": [{"label": "Coverage equity", "level": "medium"}],
        },
        headers=auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agentPaused"] is True
    assert body["waveSize"] == 5
    weights = {w["label"]: w["level"] for w in body["rankingWeights"]}
    assert weights["Coverage equity"] == "medium"

    # Persisted: a follow-up GET shows the same values.
    follow_up = await client.get(
        f"/api/locations/{LOCATION_ID}/settings", headers=auth_headers()
    )
    assert follow_up.json()["agentPaused"] is True


async def test_rescues_list_with_previews(client) -> None:
    response = await client.get("/api/rescues", headers=auth_headers())
    assert response.status_code == 200
    cases = response.json()
    assert len(cases) == 1
    case = cases[0]
    assert case["id"] == RESCUE_ID
    assert case["shiftId"] == "shift_1"
    assert case["absentEmployeeName"] == "Ana Floor"
    assert case["status"] == "OFFERING"
    assert case["waveCurrent"] == 1
    assert case["waveTotal"] == 3
    previews = {p["employeeName"]: p["status"] for p in case["offerPreviews"]}
    assert previews == {"Bruno Bar": "pending", "Carla Kitchen": "declined"}
    await assert_no_health_leak(response)


async def test_rescues_status_filter(client) -> None:
    response = await client.get(
        "/api/rescues", params={"status": "OPEN"}, headers=auth_headers()
    )
    assert response.json() == []
    response = await client.get(
        "/api/rescues", params={"status": "OFFERING"}, headers=auth_headers()
    )
    assert len(response.json()) == 1


async def test_rescue_detail(client) -> None:
    response = await client.get(f"/api/rescues/{RESCUE_ID}", headers=auth_headers())
    assert response.status_code == 200
    detail = response.json()
    assert detail["rescue"]["id"] == RESCUE_ID
    assert detail["shift"]["id"] == "shift_1"
    assert detail["shift"]["status"] == "absent"
    assert [event["type"] for event in detail["timeline"]] == ["RESCUE_OPENED"]
    # Ordered by wave, then sent_at: the declined offer (25 min ago) precedes
    # the pending one (20 min ago).
    assert [offer["status"] for offer in detail["offers"]] == ["DECLINED", "PENDING"]
    assert {c["name"] for c in detail["candidates"]} == {"Bruno Bar", "Carla Kitchen"}
    assert detail["offers"][1]["employeeName"] == "Bruno Bar"
    await assert_no_health_leak(response)


async def test_rescue_detail_404(client) -> None:
    response = await client.get("/api/rescues/res_missing", headers=auth_headers())
    assert response.status_code == 404


async def test_close_rescue_enqueues_and_answers_202(client, stub_close) -> None:
    response = await client.post(
        f"/api/rescues/{RESCUE_ID}/close", headers=auth_headers()
    )
    assert response.status_code == 202
    assert stub_close.calls == [(RESCUE_ID, MANAGER_ID)]


async def test_close_rescue_enqueue_failure_answers_500(client, stub_close) -> None:
    stub_close.error = RuntimeError("broker down")
    response = await client.post(
        f"/api/rescues/{RESCUE_ID}/close", headers=auth_headers()
    )
    assert response.status_code == 500


async def test_approvals_list(client) -> None:
    response = await client.get("/api/approvals", headers=auth_headers())
    assert response.status_code == 200
    approvals = response.json()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["id"] == APPROVAL_ID
    assert approval["kind"] == "overtime"
    assert approval["status"] == "pending"
    assert approval["context"]["employeeName"] == "Bruno Bar"
    assert approval["context"]["shiftTime"] == f"{SHIFT_START}-{SHIFT_END}"
    assert approval["expiresAt"] is not None
    await assert_no_health_leak(response)


async def test_approve_and_reject_enqueue_202(client, stub_approval) -> None:
    approve = await client.post(
        f"/api/approvals/{APPROVAL_ID}/approve", headers=auth_headers()
    )
    reject = await client.post(
        f"/api/approvals/{APPROVAL_ID}/reject", headers=auth_headers(MANAGER_ID)
    )
    assert approve.status_code == 202
    assert reject.status_code == 202
    assert stub_approval.calls == [
        (APPROVAL_ID, "approved", MANAGER_ID),
        (APPROVAL_ID, "rejected", MANAGER_ID),
    ]


async def test_approval_enqueue_failure_answers_500(client, stub_approval) -> None:
    stub_approval.error = RuntimeError("broker down")
    response = await client.post(
        f"/api/approvals/{APPROVAL_ID}/approve", headers=auth_headers()
    )
    assert response.status_code == 500


async def test_approval_unknown_id_404(client, stub_approval) -> None:
    response = await client.post("/api/approvals/apr_missing/approve", headers=auth_headers())
    assert response.status_code == 404
    assert stub_approval.calls == []


async def test_conversations_list(client) -> None:
    response = await client.get("/api/conversations", headers=auth_headers())
    assert response.status_code == 200
    conversations = response.json()
    assert [c["id"] for c in conversations] == ["conv_2", CONVERSATION_ID]
    first = conversations[1]
    assert first["employeeName"] == "Ana Floor"
    assert first["initials"] == "AF"
    assert first["lastMessage"] == "Gracias Ana, ya me encargo de buscar a alguien."
    assert first["intent"] == "ABSENCE_REPORT"
    assert first["hasRescue"] is True
    assert first["rescueLabel"].startswith("Floor")
    second = conversations[0]
    assert second["hasRescue"] is False
    assert second["rescueLabel"] == "No rescue"
    await assert_no_health_leak(response)


async def test_conversations_filters(client) -> None:
    only_with_rescue = await client.get(
        "/api/conversations", params={"has_rescue": True}, headers=auth_headers()
    )
    assert [c["id"] for c in only_with_rescue.json()] == [CONVERSATION_ID]

    by_employee = await client.get(
        "/api/conversations", params={"employee_id": "emp_2"}, headers=auth_headers()
    )
    assert [c["id"] for c in by_employee.json()] == ["conv_2"]

    by_location = await client.get(
        "/api/conversations", params={"location_id": LOCATION_ID}, headers=auth_headers()
    )
    assert len(by_location.json()) == 2

    other_location = await client.get(
        "/api/conversations", params={"location_id": "loc_other"}, headers=auth_headers()
    )
    assert other_location.json() == []


async def test_conversation_messages(client) -> None:
    response = await client.get(
        f"/api/conversations/{CONVERSATION_ID}/messages", headers=auth_headers()
    )
    assert response.status_code == 200
    messages = response.json()
    assert [m["from"] for m in messages] == ["employee", "assistant"]
    # Stored redacted bodies only (spec §10).
    assert messages[0]["text"] == "me encuentro fatal"
    assert messages[0]["interpretation"]["intent"] == "ABSENCE_REPORT"
    assert messages[0]["interpretation"]["model"] == "test-model"
    assert messages[1]["interpretation"] is None
    await assert_no_health_leak(response)


async def test_conversation_messages_404(client) -> None:
    response = await client.get("/api/conversations/conv_missing/messages", headers=auth_headers())
    assert response.status_code == 404


async def test_interpretations_require_operator(client) -> None:
    forbidden = await client.get("/api/interpretations", headers=auth_headers())
    assert forbidden.status_code == 403
    allowed = await client.get(
        "/api/interpretations", headers=auth_headers(OPERATOR_ID, "operator")
    )
    assert allowed.status_code == 200


async def test_interpretations_rows_and_filters(client) -> None:
    response = await client.get(
        "/api/interpretations", headers=auth_headers(OPERATOR_ID, "operator")
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["intent"] == "ABSENCE_REPORT"
    assert row["confidence"] == 0.92
    assert row["model"] == "test-model"
    assert row["validation"] == "OK"
    assert row["employeeName"] == "Ana Floor"
    assert row["costUsd"] == 0.001
    assert row["latencyMs"] == 400

    filtered = await client.get(
        "/api/interpretations",
        params={"intent": "OFFER_DECLINE"},
        headers=auth_headers(OPERATOR_ID, "operator"),
    )
    assert filtered.json() == []

    low = await client.get(
        "/api/interpretations",
        params={"min_confidence": 0.99},
        headers=auth_headers(OPERATOR_ID, "operator"),
    )
    assert low.json() == []

    failed = await client.get(
        "/api/interpretations",
        params={"validation_failed": True},
        headers=auth_headers(OPERATOR_ID, "operator"),
    )
    assert failed.json() == []  # 0.92 clears the 0.75 threshold


async def test_interpretation_detail(client) -> None:
    response = await client.get(
        f"/api/interpretations/{INTERPRETATION_ID}",
        headers=auth_headers(OPERATOR_ID, "operator"),
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["intent"] == "ABSENCE_REPORT"
    assert detail["promptVersion"] == "v1"
    assert detail["inputTokens"] == 120
    assert detail["outputTokens"] == 30
    assert detail["input"] == "me encuentro fatal"  # redacted body only
    assert detail["output"] == {"contains_health_details": True}
    assert detail["traceUrl"] is None  # no trace id stored -> no invented link


async def test_interpretation_detail_404(client) -> None:
    response = await client.get(
        "/api/interpretations/interp_missing",
        headers=auth_headers(OPERATOR_ID, "operator"),
    )
    assert response.status_code == 404


async def test_metrics(client) -> None:
    response = await client.get("/api/metrics", headers=auth_headers())
    assert response.status_code == 200
    metrics = response.json()
    assert [day["date"] for day in metrics["costPerDay"]] == [METRICS_DAY]
    assert metrics["costPerDay"][0]["costUsd"] == 0.001
    assert metrics["p50LatencyMs"] == 400.0
    assert metrics["p95LatencyMs"] == 400.0
    assert metrics["lowConfidencePct"] == 0.0
    assert metrics["lowConfidenceTotal"] == 0
    assert metrics["deliveryFailures"] == 0
    # Active rescue whose last audit event is 30 min old -> stuck.
    assert metrics["stuckRescues"] == 1
    await assert_no_health_leak(response)


async def test_metrics_location_filter_excludes_other_locations(client) -> None:
    response = await client.get(
        "/api/metrics", params={"location_id": "loc_other"}, headers=auth_headers()
    )
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["costPerDay"] == []
    assert metrics["stuckRescues"] == 0
