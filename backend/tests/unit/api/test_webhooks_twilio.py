"""Webhook endpoint tests (spec §7.5): signature validation, routing and
status callbacks."""

import base64
import hashlib
import hmac
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.webhooks_twilio import (
    TwilioInboundService,
    get_twilio_service,
)
from app.api.webhooks_twilio import (
    router as twilio_router,
)
from app.db.models import Base, Employee, Message

AUTH_TOKEN = "test_auth_token"
URL = "http://testserver/webhooks/twilio/inbound"


def sign(url: str, params: dict[str, str], token: str = AUTH_TOKEN) -> str:
    data = url.encode() + b"".join(
        key.encode() + value.encode() for key, value in sorted(params.items())
    )
    return base64.b64encode(hmac.new(token.encode(), data, hashlib.sha1).digest()).decode()


class FakeService:
    def __init__(self) -> None:
        self.inbound: list[tuple[str, str, str]] = []
        self.statuses: list[tuple[str, str]] = []

    async def handle(self, from_phone: str, message_sid: str, body: str) -> bool:
        self.inbound.append((from_phone, message_sid, body))
        return True

    async def update_status(self, message_sid: str, status: str) -> None:
        self.statuses.append((message_sid, status))


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setenv("TWILIO_VALIDATE_SIGNATURE", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    app = FastAPI()
    app.include_router(twilio_router)
    service = FakeService()
    app.dependency_overrides[get_twilio_service] = lambda: service
    client = TestClient(app)
    client.fake_service = service  # type: ignore[attr-defined]
    return client


def test_inbound_with_valid_signature_is_accepted(client) -> None:
    params = {
        "Body": "hola, hoy no puedo ir",
        "From": "whatsapp:+34600000001",
        "MessageSid": "SM111",
    }
    response = client.post(
        "/webhooks/twilio/inbound",
        data=params,
        headers={"X-Twilio-Signature": sign(URL, params)},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert client.fake_service.inbound == [
        ("+34600000001", "SM111", "hola, hoy no puedo ir")
    ]


def test_inbound_with_invalid_signature_is_rejected(client) -> None:
    response = client.post(
        "/webhooks/twilio/inbound",
        data={"Body": "hola", "From": "whatsapp:+34600000001", "MessageSid": "SM1"},
        headers={"X-Twilio-Signature": "forged"},
    )
    assert response.status_code == 403
    assert client.fake_service.inbound == []


def test_inbound_without_signature_is_rejected(client) -> None:
    response = client.post(
        "/webhooks/twilio/inbound",
        data={"Body": "hola", "From": "whatsapp:+34600000001", "MessageSid": "SM1"},
    )
    assert response.status_code == 403


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
    assert client.fake_service.inbound == [("+34600000001", "SM999", "hola")]


def test_status_callback_updates_delivery(client) -> None:
    params = {"MessageSid": "SM111", "MessageStatus": "delivered"}
    response = client.post(
        "/webhooks/twilio/status",
        data=params,
        headers={"X-Twilio-Signature": sign("http://testserver/webhooks/twilio/status", params)},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert client.fake_service.statuses == [("SM111", "delivered")]


class FakeOrchestrator:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def handle_inbound(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


@pytest.fixture()
async def service_world():
    import os
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            Employee(
                id="emp_1",
                location_id="loc",
                full_name="Marta L.",
                phone_e164="+34600000001",
                language="es",
                roles=["floor"],
                contract_weekly_hours=30,
                max_weekly_hours=40,
                home_zone="port",
                accepts_extra_shifts=True,
                active=True,
            )
        )
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
    yield factory, FakeOrchestrator()
    await engine.dispose()


async def test_service_routes_inbound_to_the_orchestrator(service_world) -> None:
    factory, orchestrator = service_world
    service = TwilioInboundService(factory, orchestrator)

    handled = await service.handle("+34600000001", "SM222", "sí")

    assert handled is True
    assert orchestrator.calls[0]["employee_id"] == "emp_1"
    assert orchestrator.calls[0]["provider_message_id"] == "SM222"
    assert orchestrator.calls[0]["conversation_id"] == "conv_twilio_+34600000001"


async def test_service_ignores_unknown_senders(service_world) -> None:
    factory, orchestrator = service_world
    service = TwilioInboundService(factory, orchestrator)

    handled = await service.handle("+34999999999", "SM333", "hola")

    assert handled is False
    assert orchestrator.calls == []


async def test_service_updates_delivery_status(service_world) -> None:
    factory, orchestrator = service_world
    service = TwilioInboundService(factory, orchestrator)

    await service.update_status("SM111", "delivered")

    async with factory() as session:
        message = (
            await session.execute(select(Message).where(Message.provider_message_id == "SM111"))
        ).scalar_one()
        assert message.delivery_status == "delivered"
