"""RescueOrchestrator (spec §2, §7.4): coordinates domain and ports.

Inbound handling is idempotent by provider_message_id; heavy work never runs
inside the webhook. External effects happen after state is persisted, and
every state change writes an AuditEvent (invariant 6, §5.4).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.channels.templates import render
from app.core.clock import Clock
from app.db.models import (
    ApprovalRequest,
    AuditEvent,
    Conversation,
    Employee,
    Location,
    LocationSettings,
    Manager,
    Message,
    Offer,
    RescueCase,
)
from app.domain.eligibility import evaluate_eligibility
from app.domain.entities import EligibilityResult, RescueSettings
from app.domain.entities import Employee as EmployeeEntity
from app.domain.parser import Intent, parse_message
from app.domain.quiet_hours import next_quiet_end, offers_allowed
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
            # Priority: absence confirmation (OPEN case), then offer acceptance,
            # then covering withdrawal; otherwise a polite redirect.
            if await self._has_open_case(employee_id):
                await self._handle_confirmation(conversation_id, employee_id)
            elif await self._try_accept_offer(employee_id) or await self._try_withdraw(employee_id):
                pass
            else:
                await self._send_out_of_scope(conversation_id, employee_id)
        elif parsed.intent == Intent.DECLINE:
            if await self._try_decline_offer(employee_id) or await self._try_withdraw(employee_id):
                pass
            else:
                await self._send_out_of_scope(conversation_id, employee_id)
        elif parsed.intent == Intent.ABSENCE_RETRACT:
            if not await self._handle_retraction(employee_id):
                await self._send_out_of_scope(conversation_id, employee_id)
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

            offered_count = await self._send_wave_offers(
                session,
                case,
                shift,
                candidates,
                wave_number=1,
                location_name=location_name,
                location_tz=location_tz,
                now=now,
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

        self._schedule_wave_tasks(case, now)

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

    async def _send_wave_offers(
        self,
        session: AsyncSession,
        case: RescueCase,
        shift: Any,
        ranked: list[RankedCandidate],
        *,
        wave_number: int,
        location_name: str,
        location_tz: str,
        now: datetime,
    ) -> int:
        quiet_start, quiet_end = await self._quiet_hours(case.location_id)
        if not offers_allowed(now, shift.starts_at, quiet_start, quiet_end):
            # Invariant 4: never send during quiet hours — defer to their end.
            deferred_at = next_quiet_end(now, quiet_end)
            self._scheduler.schedule(
                deferred_at, "send_wave", {"case_id": case.id, "wave": wave_number}
            )
            session.add(
                AuditEvent(
                    id=(
                        f"audit_{case.id}_queued_w{wave_number}_"
                        f"{int(now.timestamp())}"
                    ),
                    rescue_id=case.id,
                    type="OFFERS_QUEUED",
                    payload={
                        "wave": wave_number,
                        "deferred_to": deferred_at.isoformat(),
                    },
                    actor="system",
                )
            )
            return 0

        sent = 0
        for candidate in ranked[: self._config.wave_size]:
            employee = await self._employee(candidate.employee_id)
            if employee is None:
                continue
            offer_id = f"offer_{case.id}_w{wave_number}_{candidate.employee_id}"
            session.add(
                Offer(
                    id=offer_id,
                    rescue_id=case.id,
                    employee_id=candidate.employee_id,
                    wave_number=wave_number,
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
                    payload={"offer_id": offer_id, "wave": wave_number},
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

    # --- offer acceptance and decisions ---------------------------------------

    async def _has_open_case(self, employee_id: str) -> bool:
        async with self._sessions() as session:
            case = (
                await session.execute(
                    select(RescueCase).where(
                        RescueCase.absent_employee_id == employee_id,
                        RescueCase.status == State.OPEN.value,
                    )
                )
            ).scalars().first()
            return case is not None

    async def _try_accept_offer(self, employee_id: str) -> bool:
        now = self._clock.now()
        async with self._sessions() as session:
            offer = (
                await session.execute(
                    select(Offer)
                    .where(Offer.employee_id == employee_id, Offer.status == "PENDING")
                    .order_by(Offer.sent_at.desc())
                )
            ).scalars().first()
            if offer is None:
                # The rescue may have been covered by someone else while this
                # candidate's offer was cancelled: friendly close-out (§5.5).
                losing = (
                    await session.execute(
                        select(Offer)
                        .where(Offer.employee_id == employee_id)
                        .order_by(Offer.sent_at.desc())
                    )
                ).scalars().first()
                if losing is not None:
                    case_check = (
                        await session.execute(
                            select(RescueCase).where(RescueCase.id == losing.rescue_id)
                        )
                    ).scalar_one_or_none()
                    if case_check is not None and case_check.status == State.COVERED.value:
                        await self._reply_already_covered(employee_id)
                        return True
                return False

            # Row lock on the case serializes concurrent acceptances (spec §7.4).
            case = (
                await session.execute(
                    select(RescueCase).where(RescueCase.id == offer.rescue_id).with_for_update()
                )
            ).scalar_one()

            if case.status == State.ESCALATED.value:
                # Late acceptance after escalation: the manager decides (§5.5).
                result = transition(State.ESCALATED, StateMachineEvent.LATE_ACCEPTANCE)
                case.status = result.new_state.value
                session.add(
                    ApprovalRequest(
                        id=f"appr_late_{offer.id}",
                        rescue_id=case.id,
                        offer_id=offer.id,
                        kind="overtime" if offer.requires_approval else "schedule_change",
                        status="pending",
                    )
                )
                session.add(
                    AuditEvent(
                        id=f"audit_{offer.id}_late",
                        rescue_id=case.id,
                        type="APPROVAL_REQUESTED",
                        payload={"reason": "late_acceptance"},
                        actor=f"employee:{employee_id}",
                    )
                )
                await session.commit()
                manager = await self._manager_for(case.location_id)
                if manager is not None and manager.get("phone_e164"):
                    await self._send_template(
                        to=manager["phone_e164"],
                        template_key="manager_covered",
                        employee_name=await self._employee_name(employee_id),
                        role="—",
                        start="—",
                        end="—",
                    )
                return True

            if _utc(_aware(offer.expires_at)) < _utc(now):
                offer.status = "EXPIRED"
                session.add(
                    AuditEvent(
                        id=f"audit_{offer.id}_expired",
                        rescue_id=case.id,
                        type="OFFER_EXPIRED",
                        payload={},
                        actor="system",
                    )
                )
                await session.commit()
                await self._reply_already_covered(employee_id)
                return True

            shift = await self._workforce.get_shift(case.shift_id)
            if shift is None:
                return False

            # Revalidate eligibility before assigning (spec §2.6, invariant 2).
            revalidation = await self._revalidate(case.location_id, shift, employee_id, now)
            if not revalidation.eligible:
                offer.status = "CANCELLED"
                session.add(
                    AuditEvent(
                        id=f"audit_{offer.id}_revalidated",
                        rescue_id=case.id,
                        type="OFFER_REVALIDATION_FAILED",
                        payload={"reasons": [r.code for r in revalidation.reasons]},
                        actor="system",
                    )
                )
                await session.commit()
                await self._reply_already_covered(employee_id)
                return True

            if offer.requires_approval:
                result = transition(
                    State(case.status), StateMachineEvent.CONDITIONAL_ACCEPT
                )
                case.status = result.new_state.value
                session.add(
                    ApprovalRequest(
                        id=f"appr_{offer.id}",
                        rescue_id=case.id,
                        offer_id=offer.id,
                        kind="overtime",
                        status="pending",
                    )
                )
                session.add(
                    AuditEvent(
                        id=f"audit_{offer.id}_approval_req",
                        rescue_id=case.id,
                        type="APPROVAL_REQUESTED",
                        payload={"kind": "overtime"},
                        actor="system",
                    )
                )
                manager = await self._manager_for(case.location_id)
                location_name, location_tz = await self._location_info(case.location_id)
                await session.commit()
                # Manager must decide before the rescue deadline (§4.2).
                self._scheduler.schedule(
                    _aware(case.deadline_at), "approval_timeout", {"case_id": case.id}
                )

                employee = await self._employee(employee_id)
                if employee is not None and manager is not None:
                    await self._send_template(
                        to=self._phone_of(employee),
                        template_key="offer_pending_approval",
                        employee_name=employee["full_name"],
                        manager_name=manager["name"],
                    )
                return True

            # Unconditional accept: COVERED (invariant 1: one winner, locked row).
            result = transition(State(case.status), StateMachineEvent.UNCONDITIONAL_ACCEPT)
            case.status = result.new_state.value
            case.covering_employee_id = employee_id
            case.closed_at = now
            case.resolution = "covered"
            offer.status = "ACCEPTED"
            offer.responded_at = now
            await self._cancel_other_offers(session, case.id, offer.id)
            session.add(
                AuditEvent(
                    id=f"audit_{offer.id}_accepted",
                    rescue_id=case.id,
                    type="OFFER_ACCEPTED",
                    payload={"employee_id": employee_id},
                    actor=f"employee:{employee_id}",
                )
            )
            await session.commit()

        # Effects after commit (spec §4.2).
        await self._workforce.assign_shift(case.shift_id, employee_id)
        employee = await self._employee(employee_id)
        if employee is not None:
            location_name, location_tz = await self._location_info(case.location_id)
            await self._send_template(
                to=self._phone_of(employee),
                template_key="offer_confirmed",
                employee_name=employee["full_name"],
                start=self._fmt(shift.starts_at, location_tz),
                end=self._fmt(shift.ends_at, location_tz),
            )
        manager = await self._manager_for(case.location_id)
        if manager is not None and manager.get("phone_e164"):
            await self._send_template(
                to=manager["phone_e164"],
                template_key="manager_covered",
                employee_name=await self._employee_name(employee_id),
                role=self._role_label(shift.role),
                start=self._fmt(shift.starts_at, location_tz),
                end=self._fmt(shift.ends_at, location_tz),
            )
        return True

    async def _reply_already_covered(self, employee_id: str) -> None:
        employee = await self._employee(employee_id)
        if employee is None:
            return
        await self._send_template(
            to=self._phone_of(employee),
            template_key="offer_already_covered",
            employee_name=employee["full_name"],
        )

    async def _cancel_other_offers(
        self, session: AsyncSession, rescue_id: str, keep_offer_id: str
    ) -> None:
        pending = (
            await session.execute(
                select(Offer).where(
                    Offer.rescue_id == rescue_id,
                    Offer.status == "PENDING",
                    Offer.id != keep_offer_id,
                )
            )
        ).scalars()
        for offer in pending:
            offer.status = "CANCELLED"

    async def _revalidate(
        self, location_id: str, shift: Any, employee_id: str, now: datetime
    ) -> EligibilityResult:
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
        result = next(r for r in results if r.employee_id == employee_id)
        return result

    async def _try_decline_offer(self, employee_id: str) -> bool:
        now = self._clock.now()
        async with self._sessions() as session:
            offer = (
                await session.execute(
                    select(Offer)
                    .where(Offer.employee_id == employee_id, Offer.status == "PENDING")
                    .order_by(Offer.sent_at.desc())
                )
            ).scalars().first()
            if offer is None:
                return False
            offer.status = "DECLINED"
            offer.responded_at = now
            session.add(
                AuditEvent(
                    id=f"audit_{offer.id}_declined",
                    rescue_id=offer.rescue_id,
                    type="OFFER_DECLINED",
                    payload={},
                    actor=f"employee:{employee_id}",
                )
            )
            await session.commit()
            return True

    async def _try_withdraw(self, employee_id: str) -> bool:
        now = self._clock.now()
        async with self._sessions() as session:
            case = (
                await session.execute(
                    select(RescueCase).where(
                        RescueCase.covering_employee_id == employee_id,
                        RescueCase.status == State.COVERED.value,
                    )
                )
            ).scalars().first()
            if case is None:
                return False
            result = transition(State.COVERED, StateMachineEvent.COVERING_WITHDREW)
            case.status = result.new_state.value
            case.covering_employee_id = None
            case.closed_at = None
            case.resolution = None
            session.add(
                AuditEvent(
                    id=f"audit_{case.id}_withdrew_{int(now.timestamp())}",
                    rescue_id=case.id,
                    type="COVERING_WITHDREW",
                    payload={},
                    actor=f"employee:{employee_id}",
                )
            )
            await session.commit()

        await self._workforce.unassign_shift(case.shift_id)
        manager = await self._manager_for(case.location_id)
        if manager is not None and manager.get("phone_e164"):
            await self._send_template(
                to=manager["phone_e164"],
                template_key="manager_covered",
                employee_name=await self._employee_name(employee_id),
                role="—",
                start="—",
                end="—",
            )
        return True

    async def _handle_retraction(self, employee_id: str) -> bool:
        now = self._clock.now()
        async with self._sessions() as session:
            case = (
                await session.execute(
                    select(RescueCase).where(
                        RescueCase.absent_employee_id == employee_id,
                        RescueCase.status.in_(
                            [State.OFFERING.value, State.AWAITING_APPROVAL.value]
                        ),
                    )
                )
            ).scalars().first()
            if case is None:
                return False
            session.add(
                ApprovalRequest(
                    id=f"appr_cancel_{case.id}_{int(now.timestamp())}",
                    rescue_id=case.id,
                    offer_id=None,
                    kind="cancel_rescue",
                    status="pending",
                )
            )
            session.add(
                AuditEvent(
                    id=f"audit_{case.id}_cancel_req_{int(now.timestamp())}",
                    rescue_id=case.id,
                    type="APPROVAL_REQUESTED",
                    payload={"kind": "cancel_rescue"},
                    actor=f"employee:{employee_id}",
                )
            )
            await session.commit()

        manager = await self._manager_for(case.location_id)
        if manager is not None and manager.get("phone_e164"):
            shift = await self._workforce.get_shift(case.shift_id)
            location_name, location_tz = await self._location_info(case.location_id)
            await self._send_template(
                to=manager["phone_e164"],
                template_key="manager_cancel_requested",
                employee_name=await self._employee_name(employee_id),
                role=self._role_label(shift.role) if shift else "—",
                start=self._fmt(shift.starts_at, location_tz) if shift else "—",
                end=self._fmt(shift.ends_at, location_tz) if shift else "—",
            )
        return True

    async def decide_approval(self, approval_id: str, decision: str, decided_by: str) -> None:
        """Manager decision on an approval request (spec §2.1: human decides)."""
        now = self._clock.now()
        async with self._sessions() as session:
            approval = (
                await session.execute(
                    select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
                )
            ).scalar_one_or_none()
            if approval is None or approval.status != "pending":
                return
            case = (
                await session.execute(
                    select(RescueCase)
                    .where(RescueCase.id == approval.rescue_id)
                    .with_for_update()
                )
            ).scalar_one()
            state = State(case.status)

            if decision == "rejected":
                result = transition(state, StateMachineEvent.APPROVAL_REJECTED)
                approval.status = "rejected"
                offer = await self._offer(session, approval.offer_id)
                if offer is not None:
                    offer.status = "CANCELLED"
                session.add(
                    AuditEvent(
                        id=f"audit_{approval.id}_decided",
                        rescue_id=case.id,
                        type="APPROVAL_DECIDED",
                        payload={"decision": "rejected"},
                        actor=f"manager:{decided_by}",
                    )
                )
                case.status = result.new_state.value
                await session.commit()
                return

            if approval.kind == "cancel_rescue":
                result = transition(state, StateMachineEvent.APPROVAL_APPROVED_CANCEL)
                case.status = result.new_state.value
                case.closed_at = now
                case.resolution = "cancelled"
                approval.status = "approved"
                approval.decided_by = decided_by
                approval.decided_at = now
                await self._supersede_offers(session, case.id)
                session.add(
                    AuditEvent(
                        id=f"audit_{approval.id}_decided",
                        rescue_id=case.id,
                        type="APPROVAL_DECIDED",
                        payload={"decision": "approved", "kind": "cancel_rescue"},
                        actor=f"manager:{decided_by}",
                    )
                )
                await session.commit()
                return

            if approval.kind == "partial_coverage":
                result = transition(state, StateMachineEvent.APPROVAL_APPROVED_PARTIAL)
                case.status = result.new_state.value
                case.resolution = "partially_covered"
            else:  # overtime
                result = transition(state, StateMachineEvent.APPROVAL_APPROVED)
                case.status = result.new_state.value
                case.resolution = "covered"

            approval.status = "approved"
            approval.decided_by = decided_by
            approval.decided_at = now
            offer = await self._offer(session, approval.offer_id)
            if offer is not None:
                offer.status = "ACCEPTED"
                offer.responded_at = now
                case.covering_employee_id = offer.employee_id
                case.closed_at = now
                await self._cancel_other_offers(session, case.id, offer.id)
            session.add(
                AuditEvent(
                    id=f"audit_{approval.id}_decided",
                    rescue_id=case.id,
                    type="APPROVAL_DECIDED",
                    payload={"decision": "approved", "kind": approval.kind},
                    actor=f"manager:{decided_by}",
                )
            )
            await session.commit()

        # Effects after commit.
        if offer is not None and offer.employee_id:
            await self._workforce.assign_shift(case.shift_id, offer.employee_id)
            employee = await self._employee(offer.employee_id)
            confirmed_shift = await self._workforce.get_shift(case.shift_id)
            if employee is not None and confirmed_shift is not None:
                location_name, location_tz = await self._location_info(case.location_id)
                await self._send_template(
                    to=self._phone_of(employee),
                    template_key="offer_confirmed",
                    employee_name=employee["full_name"],
                    start=self._fmt(confirmed_shift.starts_at, location_tz),
                    end=self._fmt(confirmed_shift.ends_at, location_tz),
                )

    async def _offer(self, session: AsyncSession, offer_id: str | None) -> Offer | None:
        if offer_id is None:
            return None
        return (
            await session.execute(select(Offer).where(Offer.id == offer_id))
        ).scalar_one_or_none()

    async def _supersede_offers(self, session: AsyncSession, rescue_id: str) -> None:
        pending = (
            await session.execute(
                select(Offer).where(
                    Offer.rescue_id == rescue_id, Offer.status == "PENDING"
                )
            )
        ).scalars()
        for offer in pending:
            offer.status = "SUPERSEDED"

    def task_handlers(self) -> dict[str, Any]:
        """Task registry: SimScheduler and Celery tasks route to these."""
        return {
            "wave_timeout": self._on_wave_timeout,
            "rescue_deadline": self._on_deadline,
            "approval_timeout": self._on_approval_timeout,
            "send_wave": self._on_send_wave,
        }

    # --- scheduled handlers ----------------------------------------------------

    async def _on_wave_timeout(self, payload: dict[str, Any]) -> None:
        now = self._clock.now()
        case_id = payload["case_id"]
        async with self._sessions() as session:
            case = (
                await session.execute(select(RescueCase).where(RescueCase.id == case_id))
            ).scalar_one_or_none()
            if case is None or case.status != State.OFFERING.value:
                return  # covered / cancelled / escalated: nothing to do
            queued = (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.rescue_id == case.id,
                        AuditEvent.type == "OFFERS_QUEUED",
                    )
                )
            ).scalars().first()
            if queued is not None:
                return  # a deferred send_wave owns the next offer batch
            if _aware(case.deadline_at) <= now:
                await self._escalate(session, case, StateMachineEvent.DEADLINE_REACHED)
                await session.commit()
                await self._notify_escalation(case)
                return

            shift = await self._workforce.get_shift(case.shift_id)
            if shift is None:
                return
            ranked = await self._compute_candidates(case.location_id, shift, now)
            offered_ids = {
                o.employee_id
                for o in (
                    await session.execute(select(Offer).where(Offer.rescue_id == case.id))
                ).scalars()
            }
            next_candidates = [c for c in ranked if c.employee_id not in offered_ids]
            if not next_candidates:
                await self._escalate(session, case, StateMachineEvent.WAVES_EXHAUSTED)
                await session.commit()
                await self._notify_escalation(case)
                return

            last_wave = (
                await session.execute(
                    select(Offer.wave_number).where(Offer.rescue_id == case.id)
                )
            ).scalars().all()
            next_wave = max(last_wave) + 1
            location_name, location_tz = await self._location_info(case.location_id)
            await self._send_wave_offers(
                session,
                case,
                shift,
                next_candidates,
                wave_number=next_wave,
                location_name=location_name,
                location_tz=location_tz,
                now=now,
            )
            await session.commit()
            self._schedule_wave_tasks(case, now)

    async def _on_deadline(self, payload: dict[str, Any]) -> None:
        async with self._sessions() as session:
            case = (
                await session.execute(
                    select(RescueCase).where(RescueCase.id == payload["case_id"])
                )
            ).scalar_one_or_none()
            if case is None or case.status != State.OFFERING.value:
                return
            await self._escalate(session, case, StateMachineEvent.DEADLINE_REACHED)
            await session.commit()
            await self._notify_escalation(case)

    async def _on_approval_timeout(self, payload: dict[str, Any]) -> None:
        async with self._sessions() as session:
            case = (
                await session.execute(
                    select(RescueCase).where(RescueCase.id == payload["case_id"])
                )
            ).scalar_one_or_none()
            if case is None or case.status != State.AWAITING_APPROVAL.value:
                return
            result = transition(State.AWAITING_APPROVAL, StateMachineEvent.APPROVAL_TIMEOUT)
            case.status = result.new_state.value
            approvals = (
                await session.execute(
                    select(ApprovalRequest).where(
                        ApprovalRequest.rescue_id == case.id,
                        ApprovalRequest.status == "pending",
                    )
                )
            ).scalars()
            for approval in approvals:
                approval.status = "expired"
            session.add(
                AuditEvent(
                    id=f"audit_{case.id}_approval_timeout_{int(self._clock.now().timestamp())}",
                    rescue_id=case.id,
                    type="APPROVAL_TIMEOUT",
                    payload={},
                    actor="system",
                )
            )
            await session.commit()

    async def _on_send_wave(self, payload: dict[str, Any]) -> None:
        """Deferred wave send (quiet-hours gate)."""
        now = self._clock.now()
        case_id = payload["case_id"]
        wave = payload.get("wave", 1)
        async with self._sessions() as session:
            case = (
                await session.execute(select(RescueCase).where(RescueCase.id == case_id))
            ).scalar_one_or_none()
            if case is None or case.status != State.OFFERING.value:
                return
            already = (
                await session.execute(
                    select(Offer).where(Offer.rescue_id == case.id, Offer.wave_number == wave)
                )
            ).scalars().first()
            if already is not None:
                return
            shift = await self._workforce.get_shift(case.shift_id)
            if shift is None:
                return
            ranked = await self._compute_candidates(case.location_id, shift, now)
            location_name, location_tz = await self._location_info(case.location_id)
            await self._send_wave_offers(
                session,
                case,
                shift,
                ranked,
                wave_number=wave,
                location_name=location_name,
                location_tz=location_tz,
                now=now,
            )
            await session.commit()

    async def _escalate(
        self, session: AsyncSession, case: RescueCase, event: StateMachineEvent
    ) -> None:
        result = transition(State.OFFERING, event)
        case.status = result.new_state.value
        session.add(
            AuditEvent(
                id=(
                    f"audit_{case.id}_escalated_"
                    f"{int(self._clock.now().timestamp())}_{event.name}"
                ),
                rescue_id=case.id,
                type="ESCALATED",
                payload={"reason": event.name},
                actor="system",
            )
        )

    async def _notify_escalation(self, case: RescueCase) -> None:
        manager = await self._manager_for(case.location_id)
        if manager is None or not manager.get("phone_e164"):
            return
        shift = await self._workforce.get_shift(case.shift_id)
        location_name, location_tz = await self._location_info(case.location_id)
        await self._send_template(
            to=manager["phone_e164"],
            template_key="manager_escalated",
            role=self._role_label(shift.role) if shift else "—",
            start=self._fmt(shift.starts_at, location_tz) if shift else "—",
            end=self._fmt(shift.ends_at, location_tz) if shift else "—",
        )

    def _schedule_wave_tasks(self, case: RescueCase, now: datetime) -> None:
        self._scheduler.schedule(
            now + timedelta(minutes=self._config.wave_interval_minutes),
            "wave_timeout",
            {"case_id": case.id},
        )
        self._scheduler.schedule(
            _aware(case.deadline_at), "rescue_deadline", {"case_id": case.id}
        )

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

    async def _quiet_hours(self, location_id: str) -> tuple[time, time]:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(LocationSettings).where(
                        LocationSettings.location_id == location_id
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return time(23, 0), time(7, 0)
        return _parse_time(row.quiet_hours_start), _parse_time(row.quiet_hours_end)

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


def _aware(moment: datetime) -> datetime:
    """SQLite drops tzinfo on storage; treat naive values as UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


__all__ = ["OrchestratorConfig", "RescueOrchestrator", "SideEffect", "State"]
