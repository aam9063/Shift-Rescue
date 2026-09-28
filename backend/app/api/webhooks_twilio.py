"""Twilio WhatsApp webhooks (spec §7.5).

Inbound: validate the request signature, parse the form and enqueue the
orchestration task — no orchestrator, interpreter or LLM in this process
(spec §7.4). Status: update delivery status by provider message id (DB only).
"""

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.channels.twilio_whatsapp import validate_twilio_signature
from app.core.config import get_settings
from app.observability.redaction import mask_phone
from app.workers.tasks import process_inbound_message

router = APIRouter(prefix="/webhooks/twilio", tags=["twilio"])

logger = structlog.get_logger(__name__)

# Twilio requires a Content-Type on every webhook response (error 12300
# otherwise); empty TwiML acknowledges without replying.
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _ack() -> Response:
    return Response(content=EMPTY_TWIML, media_type="application/xml", status_code=200)


def public_url(request: Request) -> str:
    """Reconstruct the URL Twilio signed.

    TLS terminates at the tunnel/reverse proxy (Cloudflare, ngrok, Caddy), so
    the request reaches uvicorn as http://<internal-host>; Twilio signs the
    public https URL. Forwarded headers restore it.
    """
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    url = f"{proto}://{host}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return url


async def _validated_params(request: Request) -> dict[str, str] | None:
    """Parse the form and check the Twilio signature; None when forged."""
    settings = get_settings()
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}
    if settings.twilio_validate_signature and not validate_twilio_signature(
        settings.twilio_auth_token,
        public_url(request),
        params,
        request.headers.get("X-Twilio-Signature"),
    ):
        return None
    return params


class TwilioStatusService:
    """DB-only delivery-status updates; no orchestration in the API process."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def update_status(self, message_sid: str, status: str) -> None:
        from app.db.models import Message

        async with self._sessions() as session:
            message = (
                await session.execute(
                    select(Message).where(Message.provider_message_id == message_sid)
                )
            ).scalar_one_or_none()
            if message is None:
                return
            message.delivery_status = status
            await session.commit()


def get_status_service() -> TwilioStatusService:
    """DB-only status service (overridable in tests)."""
    from app.db.session import create_engine_and_session

    _, session_factory = create_engine_and_session()
    return TwilioStatusService(session_factory)


@router.post("/inbound")
async def twilio_inbound(request: Request) -> Response:
    params = await _validated_params(request)
    if params is None:
        return Response(status_code=403)

    message_sid = params.get("MessageSid", "")
    body = params.get("Body", "")
    from_phone = params.get("From", "").replace("whatsapp:", "")
    to_sandbox = params.get("To", "")
    if not message_sid or not from_phone:
        return Response(status_code=400)

    # Operational trace: which sandbox called us and who wrote (phone masked).
    logger.info(
        "twilio_inbound_received",
        sandbox=to_sandbox,
        sender=mask_phone(from_phone),
        message_sid=message_sid,
    )

    # Enqueue and answer immediately; the worker does the thinking (§7.5).
    # A broker rejection must be loud: 500 makes Twilio retry the delivery.
    try:
        process_inbound_message.delay(from_phone, message_sid, body)
    except Exception as error:
        logger.error(
            "twilio_inbound_enqueue_failed",
            message_sid=message_sid,
            error=str(error)[:200],
        )
        return Response(status_code=500)
    return _ack()


@router.post("/status")
async def twilio_status(
    request: Request,
    service: TwilioStatusService = Depends(get_status_service),
) -> Response:
    params = await _validated_params(request)
    if params is None:
        return Response(status_code=403)

    message_sid = params.get("MessageSid", "")
    status = params.get("MessageStatus", "")
    if message_sid and status:
        await service.update_status(message_sid, status)
    return _ack()
