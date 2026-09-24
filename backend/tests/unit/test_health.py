"""Unit tests for the health endpoint."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok_with_service_name() -> None:
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "shift-rescue-backend"


def test_health_reports_the_configured_environment() -> None:
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["environment"] in {"local", "test", "demo", "production"}
