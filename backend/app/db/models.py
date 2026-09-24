"""SQLAlchemy 2.0 models for every entity in spec §4.1.

Foundation kept the two seed-critical tables; this feature completes the
model. Schema separation (`workforce_mock`, `rescue`) is deferred to the
Postgres-only test round (ADR-001 consequences): SQLite-based unit tests
cannot express cross-schema DDL, so tables live in the default schema for
now with intent-bearing names.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=_uuid)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


# --- workforce_mock schema ----------------------------------------------------


class Location(Base):
    __tablename__ = "location"

    id: Mapped[str] = _pk()
    name: Mapped[str] = mapped_column(String(120), unique=True)
    timezone: Mapped[str] = mapped_column(String(40))
    address_zone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class Employee(Base):
    __tablename__ = "employee"

    id: Mapped[str] = _pk()
    location_id: Mapped[str] = mapped_column(String(36), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone_e164: Mapped[str] = mapped_column(String(20), unique=True)
    language: Mapped[str] = mapped_column(String(5), default="es")  # es | en
    roles: Mapped[list[str]] = mapped_column(JSON)  # kitchen|floor|bar|cleaning|supervisor
    contract_weekly_hours: Mapped[int] = mapped_column(Integer)
    max_weekly_hours: Mapped[int] = mapped_column(Integer)
    home_zone: Mapped[str] = mapped_column(String(80))
    accepts_extra_shifts: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created_at()


class Shift(Base):
    __tablename__ = "shift"

    id: Mapped[str] = _pk()
    location_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # scheduled | absent | open | covered
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    created_at: Mapped[datetime] = _created_at()


class AvailabilityBlock(Base):
    __tablename__ = "availability_block"

    id: Mapped[str] = _pk()
    employee_id: Mapped[str] = mapped_column(String(36), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(20))  # unavailable | preferred_off
    created_at: Mapped[datetime] = _created_at()


# --- rescue schema ------------------------------------------------------------


class RescueCase(Base):
    __tablename__ = "rescue_case"

    id: Mapped[str] = _pk()
    location_id: Mapped[str] = mapped_column(String(36), index=True)
    shift_id: Mapped[str] = mapped_column(String(36), index=True)
    absent_employee_id: Mapped[str] = mapped_column(String(36))
    origin: Mapped[str] = mapped_column(String(30))  # employee_message | manager_dashboard
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(40), nullable=True)
    covering_employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = _created_at()


class Offer(Base):
    __tablename__ = "offer"

    id: Mapped[str] = _pk()
    rescue_id: Mapped[str] = mapped_column(String(36), index=True)
    employee_id: Mapped[str] = mapped_column(String(36), index=True)
    wave_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    # PENDING | ACCEPTED | DECLINED | COUNTER_PROPOSED | EXPIRED
    # CANCELLED | SUPERSEDED | WITHDRAWN
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proposed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proposed_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[str] = _pk()
    employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    manager_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    channel: Mapped[str] = mapped_column(String(20))  # whatsapp | simulated | dashboard
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (UniqueConstraint("provider_message_id", name="uq_message_provider_id"),)

    id: Mapped[str] = _pk()
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # inbound | outbound
    provider_message_id: Mapped[str] = mapped_column(String(80))
    body_redacted: Mapped[str] = mapped_column(Text)
    template_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(20), default="pending")
    rescue_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = _created_at()


class Interpretation(Base):
    __tablename__ = "interpretation"

    id: Mapped[str] = _pk()
    message_id: Mapped[str] = mapped_column(String(36), index=True)
    intent: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    model: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(30))
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = _created_at()


class ApprovalRequest(Base):
    __tablename__ = "approval_request"

    id: Mapped[str] = _pk()
    rescue_id: Mapped[str] = mapped_column(String(36), index=True)
    offer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # overtime | partial_coverage | schedule_change | cancel_rescue
    kind: Mapped[str] = mapped_column(String(30))
    # pending | approved | rejected | expired
    status: Mapped[str] = mapped_column(String(20), default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[str] = _pk()
    rescue_id: Mapped[str] = mapped_column(String(36), index=True)
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # system | llm | employee:<id> | manager:<id>
    actor: Mapped[str] = mapped_column(String(60), default="system")
    created_at: Mapped[datetime] = _created_at()


class Manager(Base):
    __tablename__ = "manager"

    id: Mapped[str] = _pk()
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True)
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="manager")  # manager | operator
    created_at: Mapped[datetime] = _created_at()


class EvalRun(Base):
    __tablename__ = "eval_run"

    id: Mapped[str] = _pk()
    git_sha: Mapped[str] = mapped_column(String(40))
    trigger: Mapped[str] = mapped_column(String(20))  # ci | manual
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_config_json: Mapped[dict] = mapped_column("model_config", JSON, default=dict)
    prompt_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    invariant_violations: Mapped[dict] = mapped_column(JSON, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    baseline_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class LocationSettings(Base):
    __tablename__ = "location_settings"

    location_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    wave_size: Mapped[int] = mapped_column(Integer, default=3)
    wave_interval_minutes: Mapped[int] = mapped_column(Integer, default=10)
    rescue_deadline_minutes_before_start: Mapped[int] = mapped_column(Integer, default=30)
    min_rest_hours: Mapped[int] = mapped_column(Integer, default=12)
    max_coverages_per_14_days: Mapped[int] = mapped_column(Integer, default=4)
    quiet_hours_start: Mapped[str] = mapped_column(String(5), default="23:00")
    quiet_hours_end: Mapped[str] = mapped_column(String(5), default="07:00")
    ranking_weights: Mapped[dict] = mapped_column(JSON, default=dict)
    agent_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created_at()
