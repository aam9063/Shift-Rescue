"""Status probe tests (spec §9.3): configuration plus the worker snapshot.

The probe never reaches into the worker's objects: it reads its own settings
and the Redis snapshot. Redis failures are tolerated, never fatal.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from structlog.testing import capture_logs

from app.agent.factory import is_provider_configured
from app.api.status import StatusProbe, get_status_probe, read_runtime_snapshot
from app.api.status import router as status_router
from app.core.config import Settings
from app.observability.status import AGENT_PAUSED, LLM_CIRCUIT_OPEN, LLM_NOT_CONFIGURED


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {"_env_file": None}
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


# --- is_provider_configured: one source of truth ------------------------------


def test_provider_configured_when_enabled_and_key_present() -> None:
    settings = make_settings(llm_provider="openai", openai_api_key="sk-test")
    assert is_provider_configured(settings) is True


def test_provider_not_configured_when_disabled() -> None:
    settings = make_settings(llm_provider="none", openai_api_key="sk-test")
    assert is_provider_configured(settings) is False


def test_provider_not_configured_when_credential_missing() -> None:
    settings = make_settings(llm_provider="openai", openai_api_key="")
    assert is_provider_configured(settings) is False


def test_bedrock_needs_no_static_credential() -> None:
    settings = make_settings(llm_provider="bedrock")
    assert is_provider_configured(settings) is True


def test_unknown_provider_is_not_configured() -> None:
    settings = make_settings(llm_provider="mistral", openai_api_key="sk-test")
    assert is_provider_configured(settings) is False


# --- snapshot reading ---------------------------------------------------------


class FakeRedis:
    def __init__(self, value: bytes | None = None, error: Exception | None = None) -> None:
        self._value = value
        self._error = error

    def get(self, key: str) -> bytes | None:
        if self._error is not None:
            raise self._error
        return self._value


def test_snapshot_present_reports_the_worker_state() -> None:
    snapshot = read_runtime_snapshot(
        FakeRedis(b'{"circuit_open": true, "agent_paused": true, "llm_configured": true}')
    )
    assert snapshot == {"circuit_open": True, "agent_paused": True, "llm_configured": True}


def test_snapshot_absent_means_no_degradation() -> None:
    assert read_runtime_snapshot(FakeRedis(None)) == {}


def test_redis_failure_is_tolerated() -> None:
    with capture_logs() as logs:
        assert read_runtime_snapshot(FakeRedis(error=RedisError("connection refused"))) == {}
    assert any(e["event"] == "runtime_snapshot_read_failed" for e in logs)


def test_malformed_snapshot_is_tolerated() -> None:
    with capture_logs():
        assert read_runtime_snapshot(FakeRedis(b"not-json{")) == {}
        assert read_runtime_snapshot(FakeRedis(b'["not", "an", "object"]')) == {}


# --- probe properties ---------------------------------------------------------


def test_probe_reports_configured_provider_with_clean_snapshot() -> None:
    probe = StatusProbe(make_settings(llm_provider="openai", openai_api_key="sk-test"), {})
    assert probe.llm_configured is True
    assert probe.circuit_open is False
    assert probe.agent_paused is False


def test_probe_reports_unconfigured_provider() -> None:
    probe = StatusProbe(make_settings(llm_provider="none"), {})
    assert probe.llm_configured is False


def test_probe_reports_snapshot_degradation() -> None:
    settings = make_settings(llm_provider="openai", openai_api_key="sk-test")
    probe = StatusProbe(settings, {"circuit_open": True, "agent_paused": True})
    assert probe.circuit_open is True
    assert probe.agent_paused is True


def test_probe_endpoint_combines_configuration_and_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    app = FastAPI()
    app.include_router(status_router)

    probe = StatusProbe(
        make_settings(llm_provider="openai", openai_api_key="sk-test"),
        {"circuit_open": True},
    )
    app.dependency_overrides[get_status_probe] = lambda: probe

    with TestClient(app) as client:
        body = client.get("/api/status").json()

    assert body["degraded"] is True
    assert body["reasons"] == [LLM_CIRCUIT_OPEN]
    assert LLM_NOT_CONFIGURED not in body["reasons"]
    assert AGENT_PAUSED not in body["reasons"]
