"""Employee endpoint tests (spec §7.5, extended for the demo simulator §7.6).

`GET /api/employees?location_id=` is the list the Simulator screen renders:
display name, roles, today's shift window + status, and the conversation id
when one exists. Runs against the seeded SQLite world from `tests.conftest`.
"""

from tests.conftest import LOCATION_ID, auth_headers


async def test_employees_list_includes_shift_and_conversation(client) -> None:
    response = await client.get(
        "/api/employees", params={"location_id": LOCATION_ID}, headers=auth_headers()
    )

    assert response.status_code == 200
    employees = response.json()
    assert [employee["id"] for employee in employees] == ["emp_1", "emp_2", "emp_3"]

    ana, bruno, carla = employees
    assert ana["displayName"] == "Ana Floor"
    assert ana["roles"] == ["floor"]
    assert ana["shiftStatus"] == "absent"
    assert ana["shiftStartsAt"].endswith("+00:00")
    assert ana["shiftEndsAt"] is not None
    assert ana["conversationId"] == "conv_1"

    assert bruno["conversationId"] == "conv_2"
    assert bruno["shiftStatus"] is None  # not scheduled today in the world

    assert carla["conversationId"] is None
    assert carla["shiftStatus"] is None


async def test_employees_list_without_a_conversation_still_lists(client) -> None:
    """The simulator needs the full roster: employees without a conversation
    must appear (sending as them creates one through the real pipeline)."""
    response = await client.get("/api/employees", headers=auth_headers())

    assert response.status_code == 200
    assert len(response.json()) == 3


async def test_employees_list_filters_by_location(client) -> None:
    response = await client.get(
        "/api/employees", params={"location_id": "loc_other"}, headers=auth_headers()
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_employees_list_requires_a_token(client) -> None:
    response = await client.get("/api/employees")

    assert response.status_code == 401
