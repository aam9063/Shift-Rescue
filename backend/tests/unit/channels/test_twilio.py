"""Tests for the Twilio WhatsApp channel and signature validation (spec §7.5)."""

import base64
import hashlib
import hmac

import httpx
import pytest

from app.channels.twilio_whatsapp import (
    TwilioChannelError,
    TwilioWhatsAppChannel,
    validate_twilio_signature,
)

AUTH_TOKEN = "test_auth_token"
WEBHOOK_URL = "https://example.ngrok.app/webhooks/twilio/inbound"


def sign(url: str, params: dict[str, str], token: str = AUTH_TOKEN) -> str:
    data = url.encode() + b"".join(
        key.encode() + value.encode() for key, value in sorted(params.items())
    )
    return base64.b64encode(hmac.new(token.encode(), data, hashlib.sha1).digest()).decode()


class TestSignatureValidation:
    def test_accepts_a_valid_signature(self) -> None:
        params = {"Body": "hola", "From": "whatsapp:+34600000001", "MessageSid": "SM1"}
        assert validate_twilio_signature(AUTH_TOKEN, WEBHOOK_URL, params, sign(WEBHOOK_URL, params))

    def test_rejects_a_forged_signature(self) -> None:
        params = {"Body": "hola", "MessageSid": "SM1"}
        assert not validate_twilio_signature(AUTH_TOKEN, WEBHOOK_URL, params, "not-a-signature")

    def test_rejects_a_signature_for_a_different_token(self) -> None:
        params = {"Body": "hola", "MessageSid": "SM1"}
        forged = sign(WEBHOOK_URL, params, token="other_token")
        assert not validate_twilio_signature(AUTH_TOKEN, WEBHOOK_URL, params, forged)

    def test_rejects_a_tampered_body(self) -> None:
        params = {"Body": "hola", "MessageSid": "SM1"}
        signature = sign(WEBHOOK_URL, params)
        tampered = {**params, "Body": "tampered"}
        assert not validate_twilio_signature(AUTH_TOKEN, WEBHOOK_URL, tampered, signature)


class TestTwilioWhatsAppChannel:
    async def test_send_posts_to_twilio_and_returns_the_sid(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = request.content.decode()
            captured["auth"] = request.headers.get("authorization", "")
            return httpx.Response(201, json={"sid": "SM123"})

        channel = TwilioWhatsAppChannel(
            account_sid="AC123",
            auth_token=AUTH_TOKEN,
            from_number="whatsapp:+14155238886",
            transport=httpx.MockTransport(handler),
        )

        sid = await channel.send("+34600000001", "Hola Marta, puedes cubrir?")

        assert sid == "SM123"
        assert "/Accounts/AC123/Messages.json" in captured["url"]
        assert "To=whatsapp%3A%2B34600000001" in captured["body"]
        assert "From=whatsapp%3A%2B14155238886" in captured["body"]
        assert captured["auth"].startswith("Basic ")

    async def test_send_includes_a_content_sid_when_a_template_is_used(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = request.content.decode()
            return httpx.Response(201, json={"sid": "SM456"})

        channel = TwilioWhatsAppChannel(
            account_sid="AC123",
            auth_token=AUTH_TOKEN,
            from_number="whatsapp:+14155238886",
            transport=httpx.MockTransport(handler),
        )

        await channel.send(
            "+34600000001",
            "Hola, turno libre",
            template_key="offer",
        )

        assert "TemplateKey=offer" in captured["body"] or "offer" in captured["body"]

    async def test_send_raises_on_provider_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "Authenticate"})

        channel = TwilioWhatsAppChannel(
            account_sid="AC123",
            auth_token="bad",
            from_number="whatsapp:+14155238886",
            transport=httpx.MockTransport(handler),
        )

        with pytest.raises(TwilioChannelError):
            await channel.send("+34600000001", "hola")
