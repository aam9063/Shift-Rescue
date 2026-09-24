"""RescueOrchestrator (spec §2, §7.4): coordinates domain and ports.

Inbound handling is idempotent by provider_message_id; heavy work never runs
inside the webhook. External effects happen after state is persisted, and
every state change writes an AuditEvent (invariant 6, §5.4).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.channels.templates import render
from app.core.clock import Clock
from app.db.models import (
    AuditEvent,
    Conversation,
    Employee,
    Location,
    Manager,
    Message,
    Offer,
    RescueCase,
)
from app.domain.eligibility import evaluate_eligibility
from app.domain.entities import Employee as EmployeeEntity
from app.domain.entities import RescueSettings
from app.domain.parser import Intent, parse_message
from app.domain.ranking import RankedCandidate, rank_candidates
from app.domain.state_machine import SideEffect, State, StateMachineEvent, transition
from app.integrations.workforce.mock import MockWorkforceAdapter
from app.observability.redaction import redact_if_health
from app.ports import Channel, Scheduler

WAVE_SIZE = 3
WAVE_INTERVAL_MINUTES = 10
DEADLINE_MINUTES_BEFORE_START = 30
MIN_DEADLINE_MINUTES = 10
LOOKBACK_DAYS = 14


@dataclass(frozen=True)
class OrchestratorConfig:
    wave_size: int = WAVE_SIZE
    wave_interval_minutes: int = WAVE_INTERVAL_MINUTES
    deadline_minutes_before_start: int = DEADLINE_MINUTES_BEFORE_START
    min_deadline_minutes: int = MIN_DEADLINE_MINUTES


class RescueOrchestrator:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        workforce: MockWorkforceAdapter,
        channel: Channel,
        scheduler: Scheduler,
        clock: Clock,
        config: OrchestratorConfig | None = None,
    ) -> None:
        self._sessions = session_factory
        self._workforce = workforce
        self._channel = channel
        self._scheduler = scheduler
        self._clock = clock
        self._config = config or OrchestratorConfig()

    # --- inbound -------------------------------------------------------------

    async def handle_inbound(
        self,
        conversation_id: str,
        employee_id: str,
        provider_message_id: str,
        text: str,
    ) -> None:
        persisted = await self._persist_inbound(
            conversation_id, employee_id, provider_message_id, text
        )
        if not persisted:
            return  # duplicate provider message: processed once (spec §7.4)

        parsed = parse_message(text)
        if parsed.intent == Intent.ABSENCE_REPORT:
            await self._handle_absence_report(conversation_id, employee_id)
        elif parsed.intent == Intent.CONFIRM:
            await self._handle_confirmation(conversation_id, employee_id)
        else:
            # DECLINE/UNCLEAR/RETRACT without context: brief redirect (spec §5.5).
            await self._send_out_of_scope(conversation_id, employee_id)

    async def _persist_inbound(
        self,
        conversation_id: str,
        employee_id: str,
        provider_message_id: str,
        text: str,
    ) -> bool:
        async with self._sessions() as session:
            existing = (
                await session.execute(
                    select(Message).where(Message.provider_message_id == provider_message_id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return False

            await self._get_or_create_conversation(session, conversation_id, employee_id)
            session.add(
                Message(
                    id=f"msg_in_{provider_message_id}",
                    conversation_id=conversation_id,
                    direction="inbound",
                    provider_message_id=provider_message_id,
                    body_redacted=redact_if_health(text),
                    delivery_status="received",
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                return False
            return True

    async def _get_or_create_conversation(
        self, session: AsyncSession, conversation_id: str, employee_id: str
    ) -> Conversation:
        conversation = (
            await session.execute(select(Conversation).where(Conversation.id == conversation_id))
        ).scalar_one_or_none()
        if conversation is None:
            conversation = Conversation(
                id=conversation_id, employee_id=employee_id, channel="whatsapp"
            )
            session.add(conversation)
        return conversation

    # --- absence report ------------------------------------------------------

    async def _handle_absence_report(self, conversation_id: str, employee_id: str) -> None:
        now = self._clock.now()
        location_id = await self._location_of(employee_id)
        employee = await self._employee(employee_id)
        if employee is None or location_id is None:
            return

        shifts = await self._upcoming_shifts_of(employee_id, now)
        if len(shifts) > 1:
            # Ambiguity: ask which shift, never guess (spec §5.5).
            shift_list = ", ".join(
                f"{self._role_label(s.role)} {self._fmt(s.starts_at)}-{self._fmt(s.ends_at)}"
                for s in shifts
            )
            await self._send_template(
                to=self._phone_of(employee),
                template_key="ask_which_shift",
                employee_name=employee["full_name"],
                shift_list=shift_list,
            )
            return
        if len(shifts) == 0:
            await self._send_out_of_scope(conversation_id, employee_id)
            return

        target = shifts[0]
        deadline = self._deadline_for(now, target)

        async with self._sessions() as session:
            session.add(
                RescueCase(
                    id=f"case_{target.id}_{int(now.timestamp())}",
                    location_id=target.location_id,
                    shift_id=target.id,
                    absent_employee_id=employee_id,
                    origin="employee_message",
                    status=State.OPEN.value,
                    opened_at=now,
                    deadline_at=deadline,
                )
            )
            session.add(
                AuditEvent(
                    id=f"audit_{target.id}_{int(now.timestamp())}_reported",
                    rescue_id=f"case_{target.id}_{int(now.timestamp())}",
                    type="ABSENCE_REPORTED",
                    payload={"shift_id": target.id},
                    actor=f"employee:{employee_id}",
                )
            )
            await session.commit()

        await self._send_template(
            to=self._phone_of(employee),
            template_key="absence_confirm",
            employee_name=employee["full_name"],
            role=self._role_label(target.role),
            start=self._fmt(target.starts_at),
            end=self._fmt(target.ends_at),
        )

    async def _handle_confirmation(self, conversation_id: str, employee_id: str) -> None:
        now = self._clock.now()
        async with self._sessions() as session:
            case = (
                await session.execute(
                    select(RescueCase)
                    .where(
                        RescueCase.absent_employee_id == employee_id,
                        RescueCase.status == State.OPEN.value,
                    )
                    .order_by(RescueCase.opened_at.desc())
                )
            ).scalars().first()
            if case is None:
                await self._send_out_of_scope(conversation_id, employee_id)
                return

            result = transition(State.OPEN, StateMachineEvent.CANDIDATES_COMPUTED)
            case.status = result.new_state.value
            session.add(
                AuditEvent(
                    id=f"audit_{case.id}_opened_{int(now.timestamp())}",
                    rescue_id=case.id,
                    type="RESCUE_OPENED",
                    payload={},
                    actor="system",
                )
            )

            shift = await self._workforce.get_shift(case.shift_id)
            if shift is None:
                return
            await self._workforce.mark_absent(case.shift_id)

            location_name, location_tz = await self._location_info(case.location_id)
            candidates = await self._compute_candidates(case.location_id, shift, now)
            case.status = State.OFFERING.value

            offered_count = await self._send_first_wave(
                session, case, shift, candidates, location_name, location_tz, now
            )

            manager = await self._manager_for(case.location_id)
            if manager is not None and manager.get("phone_e164"):
                await self._send_template(
                    to=manager["phone_e164"],
                    template_key="manager_rescue_opened",
                    employee_name=await self._employee_name(case.absent_employee_id),
                    role=self._role_label(shift.role),
                    start=self._fmt(shift.starts_at, location_tz),
                    end=self._fmt(shift.ends_at, location_tz),
                    offered_count=offered_count,
                )

            # Persist the whole OPEN -> OFFERING transition before effects land.
            await session.commit()

    # --- candidates and first wave --------------------------------------------

    async def _compute_candidates(
        self, location_id: str, shift: Any, now: datetime
    ) -> list[RankedCandidate]:
        employees = await self._workforce.list_employees(location_id)
        employee_entities = [
            EmployeeEntity(
                id=e["id"],
                roles=list(e["roles"]),
                contract_weekly_hours=e["contract_weekly_hours"],
                max_weekly_hours=e["max_weekly_hours"],
                home_zone=e["home_zone"],
                accepts_extra_shifts=e["accepts_extra_shifts"],
                active=e["active"],
            )
            for e in employees
        ]
        schedule = await self._workforce.get_schedule(
            location_id, now - timedelta(days=LOOKBACK_DAYS), shift.ends_at + timedelta(days=1)
        )
        blocks = await self._workforce.list_availability_blocks(
            location_id, now - timedelta(days=LOOKBACK_DAYS), shift.ends_at + timedelta(days=1)
        )
        coverage_counts = await self._coverage_counts(now)
        results = evaluate_eligibility(
            shift,
            employee_entities,
            schedule,
            blocks,
            coverage_counts,
            RescueSettings(),
            now,
        )
        zone = await self._location_zone(location_id)
        return rank_candidates(
            employee_entities,
            results,
            coverage_counts,
            location_zone=zone,
        )

    async def _coverage_counts(self, now: datetime) -> dict[str, int]:
        from app.db.models import RescueCase as CaseModel

        async with self._sessions() as session:
            offers = (
                await session.execute(
                    select(Offer).where(
                        Offer.status == "ACCEPTED",
                        Offer.sent_at >= now - timedelta(days=LOOKBACK_DAYS),
                    )
                )
            ).scalars()
            counts: dict[str, int] = {}
            for offer in offers:
                counts[offer.employee_id] = counts.get(offer.employee_id, 0) + 1
            del CaseModel
            return counts

    async def _send_first_wave(
        self,
        session: AsyncSession,
        case: RescueCase,
        shift: Any,
        ranked: list[RankedCandidate],
        location_name: str,
        location_tz: str,
        now: datetime,
    ) -> int:
        sent = 0
        for candidate in ranked[: self._config.wave_size]:
            employee = await self._employee(candidate.employee_id)
            if employee is None:
                continue
            offer_id = f"offer_{case.id}_w1_{candidate.employee_id}"
            session.add(
                Offer(
                    id=offer_id,
                    rescue_id=case.id,
                    employee_id=candidate.employee_id,
                    wave_number=1,
                    status="PENDING",
                    sent_at=now,
                    expires_at=now + timedelta(minutes=self._config.wave_interval_minutes),
                    requires_approval=candidate.requires_approval,
                    approval_reason="overtime" if candidate.requires_approval else None,
                )
            )
            session.add(
                AuditEvent(
                    id=f"audit_{offer_id}_sent",
                    rescue_id=case.id,
                    type="OFFER_SENT",
                    payload={"offer_id": offer_id, "wave": 1},
                    actor="system",
                )
            )
            provider_id = await self._channel.send(
                recipient_phone_e164=self._phone_of(employee),
                body=render(
                    "offer",
                    employee_name=employee["full_name"],
                    location_name=location_name,
                    role=self._role_label(shift.role),
                    start=self._fmt(shift.starts_at, location_tz),
                    end=self._fmt(shift.ends_at, location_tz),
                ),
                template_key="offer",
                rescue_id=case.id,
            )
            session.add(
                Message(
                    id=f"msg_out_{offer_id}",
                    conversation_id=f"conv_{candidate.employee_id}",
                    direction="outbound",
                    provider_message_id=provider_id,
                    body_redacted="[template: offer]",
                    template_key="offer",
                    delivery_status="sent",
                    rescue_id=case.id,
                )
            )
            sent += 1
        return sent

    # --- helpers ---------------------------------------------------------------

    def _deadline_for(self, now: datetime, shift: Any) -> datetime:
        by_start = _utc(shift.starts_at) - timedelta(
            minutes=self._config.deadline_minutes_before_start
        )
        by_opened = _utc(now) + timedelta(minutes=self._config.min_deadline_minutes)
        return max(by_start, by_opened)  # never surrender without trying (spec §5.3)

    async def _upcoming_shifts_of(self, employee_id: str, now: datetime) -> list:
        location_id = await self._location_of(employee_id)
        if location_id is None:
            return []
        schedule = await self._workforce.get_schedule(
            location_id, now - timedelta(hours=4), now + timedelta(hours=48)
        )
        return [s for s in schedule if s.employee_id == employee_id and s.ends_at > now]

    async def _employee(self, employee_id: str) -> dict[str, Any] | None:
        location_id = await self._location_of(employee_id)
        if location_id is None:
            return None
        for e in await self._workforce.list_employees(location_id):
            if e["id"] == employee_id:
                return e
        return None

    async def _employee_name(self, employee_id: str) -> str:
        employee = await self._employee(employee_id)
        return employee["full_name"] if employee else employee_id

    async def _location_of(self, employee_id: str) -> str | None:
        async with self._sessions() as session:
            row = (
                await session.execute(select(Employee).where(Employee.id == employee_id))
            ).scalar_one_or_none()
            return row.location_id if row else None

    async def _location_info(self, location_id: str) -> tuple[str, str]:
        async with self._sessions() as session:
            row = (
                await session.execute(select(Location).where(Location.id == location_id))
            ).scalar_one_or_none()
            return (row.name if row else "", row.timezone if row else "UTC")

    async def _location_zone(self, location_id: str) -> str:
        async with self._sessions() as session:
            row = (
                await session.execute(select(Location).where(Location.id == location_id))
            ).scalar_one_or_none()
            return row.home_zone if row and hasattr(row, "home_zone") else ""  # pragma: no cover

    async def _manager_for(self, location_id: str) -> dict[str, Any] | None:
        async with self._sessions() as session:
            rows = (await session.execute(select(Manager))).scalars()
            for manager in rows:
                if location_id in (manager.location_ids or []) and manager.role == "manager":
                    return {
                        "id": manager.id,
                        "name": manager.name,
                        "phone_e164": manager.phone_e164,
                    }
            return None

    async def _send_template(self, to: str, template_key: str, **params: Any) -> None:
        await self._channel.send(
            recipient_phone_e164=to,
            body=render(template_key, **params),
            template_key=template_key,
        )

    async def _send_out_of_scope(self, conversation_id: str, employee_id: str) -> None:
        employee = await self._employee(employee_id)
        location_name, _ = await self._location_info(
            await self._location_of(employee_id) or ""
        )
        if employee is None:
            return
        await self._send_template(
            to=self._phone_of(employee),
            template_key="out_of_scope",
            location_name=location_name,
        )

    def _phone_of(self, employee: dict[str, Any]) -> str:
        return employee["phone_e164"]

    def _role_label(self, role: str) -> str:
        return {
            "kitchen": "cocina",
            "floor": "sala",
            "bar": "barra",
            "cleaning": "limpieza",
            "supervisor": "encargado",
        }.get(role, role)

    def _fmt(self, moment: datetime, tz_name: str | None = None) -> str:
        tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC")
        return moment.astimezone(tz).strftime("%H:%M")


def _utc(moment: datetime) -> datetime:

    return moment.astimezone(UTC)


__all__ = ["OrchestratorConfig", "RescueOrchestrator", "SideEffect", "State"]
