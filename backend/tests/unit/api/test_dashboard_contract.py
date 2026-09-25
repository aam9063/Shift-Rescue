"""Contract tests: exact JSON field names vs `frontend/src/domain/types.ts`
and the shapes in `frontend/src/services/dashboardMock.ts`.

A renamed field must break these tests. Sets are compared exactly — extra or
missing keys fail.
"""


from tests.conftest import (
    CONVERSATION_ID,
    INTERPRETATION_ID,
    LOCATION_ID,
    OPERATOR_ID,
    RESCUE_ID,
    auth_headers,
)

LOGIN_KEYS = {"accessToken", "tokenType", "expiresIn", "manager"}
MANAGER_KEYS = {"id", "name", "email", "role", "locationIds"}
LOCATION_KEYS = {"id", "name", "timezone"}
SHIFT_KEYS = {"id", "locationId", "role", "startsAt", "endsAt", "assigneeName", "status"}
RESCUE_CASE_KEYS = {
    "id",
    "shiftId",
    "absentEmployeeName",
    "status",
    "deadlineAt",
    "openedAt",
    "waveCurrent",
    "waveTotal",
    "offerPreviews",
}
OFFER_PREVIEW_KEYS = {"employeeName", "status"}
AUDIT_EVENT_KEYS = {"id", "rescueId", "type", "actor", "createdAt", "interpretedByAi"}
OFFER_KEYS = {
    "id",
    "rescueId",
    "employeeId",
    "employeeName",
    "waveNumber",
    "status",
    "sentAt",
    "expiresAt",
}
CANDIDATE_KEYS = {
    "employeeId",
    "name",
    "score",
    "eligible",
    "requiresApproval",
    "reasons",
}
EXCLUSION_KEYS = {"code", "message"}
RESCUE_DETAIL_KEYS = {"rescue", "shift", "timeline", "candidates", "offers"}
APPROVAL_KEYS = {
    "id",
    "rescueId",
    "kind",
    "status",
    "requestedAt",
    "decidedBy",
    "decidedAt",
    "expiresAt",
    "context",
}
APPROVAL_CONTEXT_KEYS = {"employeeName", "shiftTime", "detail"}
CONVERSATION_KEYS = {
    "id",
    "employeeId",
    "employeeName",
    "initials",
    "lastMessage",
    "lastMessageAt",
    "intent",
    "hasRescue",
    "rescueId",
    "rescueLabel",
}
MESSAGE_KEYS = {"id", "from", "text", "createdAt", "interpretation"}
INTERPRETATION_SUMMARY_KEYS = {"intent", "confidence", "model"}
INTERPRETATION_ROW_KEYS = {
    "id",
    "time",
    "employeeName",
    "intent",
    "confidence",
    "model",
    "costUsd",
    "latencyMs",
    "validation",
}
INTERPRETATION_DETAIL_KEYS = INTERPRETATION_ROW_KEYS | {
    "promptVersion",
    "inputTokens",
    "outputTokens",
    "input",
    "output",
    "traceUrl",
}
METRICS_KEYS = {
    "costPerDay",
    "p50LatencyMs",
    "p95LatencyMs",
    "lowConfidencePct",
    "lowConfidenceTotal",
    "deliveryFailures",
    "stuckRescues",
}
DAILY_COST_KEYS = {"date", "costUsd"}
SETTINGS_KEYS = {
    "agentPaused",
    "rankingWeights",
    "waveSize",
    "waveIntervalMinutes",
    "quietStart",
    "quietEnd",
}
RANKING_WEIGHT_KEYS = {"label", "level"}


def assert_keys(payload: dict | list, expected: set, path: str = "$") -> None:
    if isinstance(payload, list):
        assert payload, f"{path}: expected at least one element"
        for index, item in enumerate(payload):
            assert_keys(item, expected, f"{path}[{index}]")
        return
    assert isinstance(payload, dict), f"{path}: expected object, got {type(payload).__name__}"
    actual = set(payload.keys())
    assert actual == expected, (
        f"{path}: field mismatch\n  missing: {expected - actual}\n  extra: {actual - expected}"
    )


async def test_login_contract(client) -> None:
    response = await client.post(
        "/api/auth/login", json={"email": "manager@test.demo", "password": "laterraza-demo-2026"}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == LOGIN_KEYS
    assert set(body["manager"]) == MANAGER_KEYS


async def test_locations_contract(client) -> None:
    response = await client.get("/api/locations", headers=auth_headers())
    assert response.status_code == 200
    assert_keys(response.json(), LOCATION_KEYS)


async def test_shift_contract(client) -> None:
    response = await client.get(
        f"/api/locations/{LOCATION_ID}/shifts", headers=auth_headers()
    )
    assert_keys(response.json(), SHIFT_KEYS)


async def test_settings_contract(client) -> None:
    response = await client.get(
        f"/api/locations/{LOCATION_ID}/settings", headers=auth_headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == SETTINGS_KEYS
    assert_keys(body["rankingWeights"], RANKING_WEIGHT_KEYS)


async def test_rescue_case_contract(client) -> None:
    response = await client.get("/api/rescues", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert_keys(body, RESCUE_CASE_KEYS)
    assert_keys(body[0]["offerPreviews"], OFFER_PREVIEW_KEYS)


async def test_rescue_detail_contract(client) -> None:
    response = await client.get(f"/api/rescues/{RESCUE_ID}", headers=auth_headers())
    assert response.status_code == 200
    detail = response.json()
    assert set(detail) == RESCUE_DETAIL_KEYS
    assert set(detail["rescue"]) == RESCUE_CASE_KEYS
    assert set(detail["shift"]) == SHIFT_KEYS
    assert_keys(detail["timeline"], AUDIT_EVENT_KEYS)
    assert_keys(detail["offers"], OFFER_KEYS)
    assert_keys(detail["candidates"], CANDIDATE_KEYS)
    for candidate in detail["candidates"]:
        assert set(candidate["reasons"]) <= EXCLUSION_KEYS


async def test_approval_contract(client) -> None:
    response = await client.get("/api/approvals", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert_keys(body, APPROVAL_KEYS)
    assert set(body[0]["context"]) == APPROVAL_CONTEXT_KEYS


async def test_conversation_contract(client) -> None:
    response = await client.get("/api/conversations", headers=auth_headers())
    assert response.status_code == 200
    assert_keys(response.json(), CONVERSATION_KEYS)


async def test_conversation_message_contract(client) -> None:
    response = await client.get(
        f"/api/conversations/{CONVERSATION_ID}/messages", headers=auth_headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert_keys(body, MESSAGE_KEYS)
    assert set(body[0]["interpretation"]) == INTERPRETATION_SUMMARY_KEYS


async def test_interpretation_row_contract(client) -> None:
    response = await client.get(
        "/api/interpretations", headers=auth_headers(OPERATOR_ID, "operator")
    )
    assert response.status_code == 200
    assert_keys(response.json(), INTERPRETATION_ROW_KEYS)


async def test_interpretation_detail_contract(client) -> None:
    response = await client.get(
        f"/api/interpretations/{INTERPRETATION_ID}",
        headers=auth_headers(OPERATOR_ID, "operator"),
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == INTERPRETATION_DETAIL_KEYS
    assert body["input"] == "me encuentro fatal"  # redacted, never the raw text


async def test_metrics_contract(client) -> None:
    response = await client.get("/api/metrics", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == METRICS_KEYS
    assert_keys(body["costPerDay"], DAILY_COST_KEYS)
