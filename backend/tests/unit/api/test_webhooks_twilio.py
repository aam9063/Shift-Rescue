"""Webhook endpoint tests (spec §7.5): signature validation, enqueue-and-return,
latency, and status callbacks. No orchestrator lives in the API process."""

import base64
import hashlib
import hmac
import os
import tempfile
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from structlog.testing import capture_logs

import app.api.webhooks_twilio as webhooks_twilio
from app.api.webhooks_twilio import (
    TwilioStatusService,
    get_status_service,
)
from app.api.webhooks_twilio import (
    router as twilio_router,
)
from app.db.models import Base, Message

AUTH_TOKEN = "test_auth_token"
URL = "http://testserver/webhooks/twilio/inbound"


def sign(url: str, params: dict[str, str], token: str = AUTH_TOKEN) -> str:
    data = url.encode() + b"".join(
        key.encode() + value.encode() for key, value in sorted(params.items())
    )
    return base64.b64encode(hmac.new(token.encode(), data, hashlib.sha1).digest()).decode()


class StubTask:
    """Stand-in for the Celery task: records `.delay` calls, can fail."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.error: Exception | None = None

    def delay(self, from_phone: str, message_sid: str, body: str) -> None:
        if self.error is not None:
            raise self.error
        self.calls.append((from_phone, message_sid, body))


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setenv("TWILIO_VALIDATE_SIGNATURE", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    app = FastAPI()
    app.include_router(twilio_router)
    stub = StubTask()
    monkeypatch.setattr(webhooks_twilio, "process_inbound_message", stub)
    client = TestClient(app)
    client.stub_task = stub  # type: ignore[attr-defined]
    return client


def test_inbound_enqueues_exactly_once_and_answers_fast(client) -> None:
    params = {
        "Body": "hola, hoy no puedo ir",
        "From": "whatsapp:+34600000001",
        "MessageSid": "SM111",
    }
    start = time.perf_counter()
    response = client.post(
        "/webhooks/twilio/inbound",
        data=params,
        headers={"X-Twilio-Signature": sign(URL, params)},
    )
    elapsed = time.perf_counter() - start

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    # Spec §7.5: the webhook answers in well under 200 ms with a stubbed enqueue.
    assert elapsed < 0.2
    assert client.stub_task.calls == [("+34600000001", "SM111", "hola, hoy no puedo ir")]


def test_inbound_with_invalid_signature_is_rejected(client) -> None:
    response = client.post(
        "/webhooks/twilio/inbound",
        data={"Body": "hola", "From": "whatsapp:+34600000001", "MessageSid": "SM1"},
        headers={"X-Twilio-Signature": "forged"},
    )
    assert response.status_code == 403
    assert client.stub_task.calls == []


def test_inbound_without_signature_is_rejected(client) -> None:
    response = client.post(
        "/webhooks/twilio/inbound",
        data={"Body": "hola", "From": "whatsapp:+34600000001", "MessageSid": "SM1"},
    )
    assert response.status_code == 403
    assert client.stub_task.calls == []


def test_inbound_behind_a_tls_proxy_uses_the_forwarded_public_url(client) -> None:
    """Cloudflare/ngrok terminate TLS: Twilio signs the https URL, so the
    signature must be validated against the forwarded public URL."""
    params = {"Body": "hola", "From": "whatsapp:+34600000001", "MessageSid": "SM999"}
    public_url = "https://masters-clarity-possible-shipped.trycloudflare.com/webhooks/twilio/inbound"
    response = client.post(
        "/webhooks/twilio/inbound",
        data=params,
        headers={
            "X-Twilio-Signature": sign(public_url, params),
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "masters-clarity-possible-shipped.trycloudflare.com",
            "Host": "masters-clarity-possible-shipped.trycloudflare.com",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert client.stub_task.calls == [("+34600000001", "SM999", "hola")]


def test_inbound_enqueue_failure_returns_500_and_logs(client) -> None:
    """A broker rejection must never drop the message as a silent 200."""
    client.stub_task.error = RuntimeError("broker down")
    params = {"Body": "hola", "From": "whatsapp:+34600000001", "MessageSid": "SM500"}

    with capture_logs() as logs:
        response = client.post(
            "/webhooks/twilio/inbound",
            data=params,
            headers={"X-Twilio-Signature": sign(URL, params)},
        )

    assert response.status_code == 500
    errors = [entry for entry in logs if entry["event"] == "twilio_inbound_enqueue_failed"]
    assert len(errors) == 1
    assert errors[0]["message_sid"] == "SM500"
    assert "broker down" in errors[0]["error"]


@pytest.fixture()
async def status_world():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            Message(
                id="msg_out_1",
                conversation_id="conv_twilio_+34600000001",
                direction="outbound",
                provider_message_id="SM111",
                body_redacted="[template: offer]",
                template_key="offer",
                delivery_status="sent",
            )
        )
        await session.commit()
    yield factory
    await engine.dispose()


class FakeStatusService:
    def __init__(self) -> None:
        self.statuses: list[tuple[str, str]] = []

    async def update_status(self, message_sid: str, status: str) -> None:
        self.statuses.append((message_sid, status))


@pytest.fixture()
def status_client(client):
    fake = FakeStatusService()
    client.app.dependency_overrides[get_status_service] = lambda: fake
    client.fake_status_service = fake  # type: ignore[attr-defined]
    return client


async def test_status_service_updates_delivery_status(status_world) -> None:
    factory = status_world
    service = TwilioStatusService(factory)

    await service.update_status("SM111", "delivered")

    async with factory() as session:
        message = (
            await session.execute(select(Message).where(Message.provider_message_id == "SM111"))
        ).scalar_one()
        assert message.delivery_status == "delivered"


async def test_status_service_ignores_unknown_messages(status_world) -> None:
    factory = status_world
    service = TwilioStatusService(factory)

    await service.update_status("SM_UNKNOWN", "delivered")  # no raise

    async with factory() as session:
        message = (
            await session.execute(select(Message).where(Message.provider_message_id == "SM111"))
        ).scalar_one()
        assert message.delivery_status == "sent"


def test_status_callback_updates_delivery(status_client) -> None:
    params = {"MessageSid": "SM111", "MessageStatus": "delivered"}
    response = status_client.post(
        "/webhooks/twilio/status",
        data=params,
        headers={
            "X-Twilio-Signature": sign("http://testserver/webhooks/twilio/status", params)
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert status_client.fake_status_service.statuses == [("SM111", "delivered")]


def test_status_callback_signature_is_enforced(status_client) -> None:
    response = status_client.post(
        "/webhooks/twilio/status",
        data={"MessageSid": "SM111", "MessageStatus": "delivered"},
        headers={"X-Twilio-Signature": "forged"},
    )
    assert response.status_code == 403
    assert status_client.fake_status_service.statuses == []
