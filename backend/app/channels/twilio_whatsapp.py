"""Twilio WhatsApp channel (spec §7.2, §7.5).

Real outbound through the Twilio REST API (httpx, no SDK) plus the inbound
signature validator. Templates outside the 24h session window require an
approved Content Template; in the sandbox the session window applies
(docs/twilio-sandbox-setup.md).
"""

import base64
import hashlib
import hmac
from typing import Any

import httpx

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


class TwilioChannelError(Exception):
    """Outbound delivery failed at the provider."""


def validate_twilio_signature(
    auth_token: str,
    url: str,
    params: dict[str, str],
    signature: str | None,
) -> bool:
    """Twilio request validation: HMAC-SHA1 over URL + sorted form params."""
    if not signature:
        return False
    payload = url.encode()
    for key, value in sorted(params.items()):
        payload += key.encode() + value.encode()
    expected = base64.b64encode(
        hmac.new(auth_token.encode(), payload, hashlib.sha1).digest()
    ).decode()
    return hmac.compare_digest(expected, signature)


class TwilioWhatsAppChannel:
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._transport = transport
        self._timeout = timeout_seconds

    async def send(
        self,
        recipient_phone_e164: str,
        body: str,
        *,
        template_key: str | None = None,
        rescue_id: str | None = None,
    ) -> str:
        data: dict[str, Any] = {
            "From": self._from_number,
            "To": f"whatsapp:{recipient_phone_e164}",
            "Body": body,
        }
        if template_key:
            # Our template key travels with the message so deliveries stay
            # traceable; approved Content SIDs plug in here for production.
            data["TemplateKey"] = template_key

        url = f"{TWILIO_API_BASE}/Accounts/{self._account_sid}/Messages.json"
        async with httpx.AsyncClient(
            auth=(self._account_sid, self._auth_token),
            transport=self._transport,
            timeout=self._timeout,
        ) as client:
            response = await client.post(url, data=data)

        if response.status_code >= 400:
            raise TwilioChannelError(
                f"Twilio rejected the message ({response.status_code}): {response.text[:200]}"
            )
        payload = response.json()
        return str(payload.get("sid", ""))
