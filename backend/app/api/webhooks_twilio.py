"""Twilio WhatsApp webhooks (spec §7.5).

Inbound: validate the request signature, map the sender phone to an employee
and hand the message to the orchestrator — fast, no LLM work here (§7.4).
Status: update delivery status by provider message id.
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.channels.twilio_whatsapp import validate_twilio_signature
from app.core.config import get_settings
from app.observability.redaction import mask_phone

router = APIRouter(prefix="/webhooks/twilio", tags=["twilio"])

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


class TwilioInboundService:
    """Maps provider messages to the domain; unknown senders are ignored."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        orchestrator: Any,
        scheduler: Any = None,
    ) -> None:
        self._sessions = session_factory
        self._orchestrator = orchestrator
        # Exposed so the app lifespan can drive due jobs while Celery wiring
        # lands (see the resilience / deploy features).
        self.scheduler = scheduler

    async def handle(self, from_phone: str, message_sid: str, body: str) -> bool:
        from app.db.models import Employee

        async with self._sessions() as session:
            employee = (
                await session.execute(
                    select(Employee).where(Employee.phone_e164 == from_phone)
                )
            ).scalar_one_or_none()
        if employee is None:
            return False

        await self._orchestrator.handle_inbound(
            conversation_id=f"conv_twilio_{from_phone}",
            employee_id=employee.id,
            provider_message_id=message_sid,
            text=body,
        )
        return True

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


_service: TwilioInboundService | None = None


def get_twilio_service() -> TwilioInboundService:
    """Runtime wiring: DB sessions + the shared orchestrator (overridable)."""
    global _service
    if _service is None:
        from app.channels.twilio_whatsapp import TwilioWhatsAppChannel
        from app.db.session import create_engine_and_session
        from app.integrations.workforce.mock import MockWorkforceAdapter
        from app.services.orchestrator import RescueOrchestrator
        from app.workers.scheduler import SimScheduler

        settings = get_settings()
        engine, session_factory = create_engine_and_session()
        channel = TwilioWhatsAppChannel(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
            from_number=settings.twilio_whatsapp_from,
        )
        scheduler = SimScheduler()
        orchestrator = RescueOrchestrator(
            session_factory=session_factory,
            workforce=MockWorkforceAdapter(session_factory),
            channel=channel,
            scheduler=scheduler,
            clock=__import__("app.core.clock", fromlist=["SystemClock"]).SystemClock(),
        )
        for name, handler in orchestrator.task_handlers().items():
            scheduler.register(name, handler)
        _service = TwilioInboundService(session_factory, orchestrator, scheduler)
    return _service


@router.post("/inbound")
async def twilio_inbound(
    request: Request,
    service: TwilioInboundService = Depends(get_twilio_service),
) -> Response:
    settings = get_settings()
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}

    if settings.twilio_validate_signature and not validate_twilio_signature(
        settings.twilio_auth_token,
        public_url(request),
        params,
        request.headers.get("X-Twilio-Signature"),
    ):
        return Response(status_code=403)

    message_sid = params.get("MessageSid", "")
    body = params.get("Body", "")
    from_phone = params.get("From", "").replace("whatsapp:", "")
    to_sandbox = params.get("To", "")
    if not message_sid or not from_phone:
        return Response(status_code=400)

    # Operational trace: which sandbox called us and who wrote (phone masked).
    structlog.get_logger(__name__).info(
        "twilio_inbound_received",
        sandbox=to_sandbox,
        sender=mask_phone(from_phone),
        message_sid=message_sid,
    )

    handled = await service.handle(from_phone, message_sid, body)
    structlog.get_logger(__name__).info(
        "twilio_inbound_handled", sandbox=to_sandbox, recognized=handled
    )
    return _ack()


@router.post("/status")
async def twilio_status(
    request: Request,
    service: TwilioInboundService = Depends(get_twilio_service),
) -> Response:
    settings = get_settings()
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}

    if settings.twilio_validate_signature and not validate_twilio_signature(
        settings.twilio_auth_token,
        public_url(request),
        params,
        request.headers.get("X-Twilio-Signature"),
    ):
        return Response(status_code=403)

    message_sid = params.get("MessageSid", "")
    status = params.get("MessageStatus", "")
    if message_sid and status:
        await service.update_status(message_sid, status)
    return _ack()
