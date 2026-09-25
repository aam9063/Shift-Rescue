"""Shared fixtures for the dashboard API tests.

A small deterministic world in a temp-file SQLite database: one location with
settings, two managers (manager + operator roles, Argon2-hashed demo
password), employees, an absent shift with an open rescue (offers + audit
event), a pending approval, conversations with messages and one persisted
interpretation. `create_app()` serves it with dependency overrides, so no
real database, Redis or broker is touched.
"""

import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.db.models import (
    ApprovalRequest,
    AuditEvent,
    Base,
    Conversation,
    Employee,
    Interpretation,
    Location,
    LocationSettings,
    Manager,
    Message,
    Offer,
    RescueCase,
    Shift,
)
from app.db.seed import DEMO_PASSWORD
from app.db.session import get_session
from app.main import create_app
from app.security.passwords import LEGACY_PLACEHOLDER_HASH, hash_password

NOW = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)

LOCATION_ID = "loc_test"
MANAGER_ID = "mgr_1"
OPERATOR_ID = "mgr_op"
ABSENT_ID = "emp_1"
SHIFT_ID = "shift_1"
RESCUE_ID = "res_1"
OFFER_PENDING_ID = "off_1"
OFFER_DECLINED_ID = "off_2"
APPROVAL_ID = "appr_1"
CONVERSATION_ID = "conv_1"
INBOUND_MESSAGE_ID = "msg_1"
INTERPRETATION_ID = "interp_1"

# 32+ bytes so PyJWT's InsecureKeyLengthWarning stays out of test output.
TEST_SETTINGS = Settings(jwt_secret="test-secret-with-at-least-32-bytes!!", _env_file=None)


def settings_override() -> Settings:
    return TEST_SETTINGS


@dataclass
class World:
    sessions: async_sessionmaker
    ids: dict[str, str] = field(default_factory=dict)


@pytest.fixture()
async def db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def build_world(sessions: async_sessionmaker) -> None:
    async with sessions() as session:
        session.add_all(
            [
                Location(id=LOCATION_ID, name="Test Bar", timezone="UTC"),
                LocationSettings(
                    location_id=LOCATION_ID,
                    ranking_weights={
                        "equity": 0.4,
                        "proximity": 0.3,
                        "preference": 0.2,
                        "no_overtime": 0.1,
                    },
                ),
                Manager(
                    id=MANAGER_ID,
                    name="Demo Manager",
                    email="manager@test.demo",
                    password_hash=hash_password(DEMO_PASSWORD),
                    role="manager",
                    location_ids=[LOCATION_ID],
                ),
                Manager(
                    id=OPERATOR_ID,
                    name="Demo Operator",
                    email="operator@test.demo",
                    password_hash=hash_password(DEMO_PASSWORD),
                    role="operator",
                    location_ids=[LOCATION_ID],
                ),
                Manager(
                    id="mgr_placeholder",
                    name="Legacy Manager",
                    email="legacy@test.demo",
                    password_hash=LEGACY_PLACEHOLDER_HASH,
                    role="manager",
                    location_ids=[LOCATION_ID],
                ),
                Employee(
                    id=ABSENT_ID,
                    location_id=LOCATION_ID,
                    full_name="Ana Floor",
                    phone_e164="+34600000001",
                    language="es",
                    roles=["floor"],
                    contract_weekly_hours=30,
                    max_weekly_hours=40,
                    home_zone="port",
                    accepts_extra_shifts=True,
                    active=True,
                ),
                Employee(
                    id="emp_2",
                    location_id=LOCATION_ID,
                    full_name="Bruno Bar",
                    phone_e164="+34600000002",
                    language="es",
                    roles=["bar"],
                    contract_weekly_hours=30,
                    max_weekly_hours=40,
                    home_zone="port",
                    accepts_extra_shifts=True,
                    active=True,
                ),
                Employee(
                    id="emp_3",
                    location_id=LOCATION_ID,
                    full_name="Carla Kitchen",
                    phone_e164="+34600000003",
                    language="es",
                    roles=["kitchen"],
                    contract_weekly_hours=30,
                    max_weekly_hours=40,
                    home_zone="port",
                    accepts_extra_shifts=True,
                    active=True,
                ),
                Shift(
                    id=SHIFT_ID,
                    location_id=LOCATION_ID,
                    role="floor",
                    starts_at=NOW + timedelta(hours=2),
                    ends_at=NOW + timedelta(hours=10),
                    employee_id=ABSENT_ID,
                    status="absent",
                ),
                RescueCase(
                    id=RESCUE_ID,
                    location_id=LOCATION_ID,
                    shift_id=SHIFT_ID,
                    absent_employee_id=ABSENT_ID,
                    origin="employee_message",
                    status="OFFERING",
                    opened_at=NOW - timedelta(minutes=30),
                    deadline_at=NOW + timedelta(minutes=30),
                    metrics={"wave_total": 3},
                ),
                Offer(
                    id=OFFER_PENDING_ID,
                    rescue_id=RESCUE_ID,
                    employee_id="emp_2",
                    wave_number=1,
                    status="PENDING",
                    sent_at=NOW - timedelta(minutes=20),
                    expires_at=NOW + timedelta(minutes=10),
                    requires_approval=True,
                    approval_reason="overtime",
                ),
                Offer(
                    id=OFFER_DECLINED_ID,
                    rescue_id=RESCUE_ID,
                    employee_id="emp_3",
                    wave_number=1,
                    status="DECLINED",
                    sent_at=NOW - timedelta(minutes=25),
                    expires_at=NOW - timedelta(minutes=5),
                ),
                AuditEvent(
                    id="audit_1",
                    rescue_id=RESCUE_ID,
                    type="RESCUE_OPENED",
                    payload={},
                    actor="system",
                    created_at=NOW - timedelta(minutes=30),
                ),
                ApprovalRequest(
                    id=APPROVAL_ID,
                    rescue_id=RESCUE_ID,
                    offer_id=OFFER_PENDING_ID,
                    kind="overtime",
                    status="pending",
                    created_at=NOW - timedelta(minutes=15),
                ),
                Conversation(
                    id=CONVERSATION_ID,
                    employee_id=ABSENT_ID,
                    channel="whatsapp",
                    last_inbound_at=NOW - timedelta(minutes=5),
                ),
                Message(
                    id=INBOUND_MESSAGE_ID,
                    conversation_id=CONVERSATION_ID,
                    direction="inbound",
                    provider_message_id="provider_msg_1",
                    body_redacted="me encuentro fatal",  # stored redacted (spec §10)
                    delivery_status="received",
                    rescue_id=RESCUE_ID,
                    created_at=NOW - timedelta(minutes=5),
                ),
                Message(
                    id="msg_2",
                    conversation_id=CONVERSATION_ID,
                    direction="outbound",
                    provider_message_id="provider_msg_2",
                    body_redacted="Gracias Ana, ya me encargo de buscar a alguien.",
                    template_key="absence_ack",
                    delivery_status="delivered",
                    created_at=NOW - timedelta(minutes=4),
                ),
                Interpretation(
                    id=INTERPRETATION_ID,
                    message_id=INBOUND_MESSAGE_ID,
                    intent="ABSENCE_REPORT",
                    confidence=0.92,
                    extracted={"contains_health_details": True},
                    model="test-model",
                    prompt_version="v1",
                    latency_ms=400,
                    input_tokens=120,
                    output_tokens=30,
                    cost_usd=0.001,
                    created_at=NOW - timedelta(minutes=5),
                ),
                Conversation(
                    id="conv_2",
                    employee_id="emp_2",
                    channel="whatsapp",
                    last_inbound_at=NOW - timedelta(minutes=1),
                ),
                Message(
                    id="msg_3",
                    conversation_id="conv_2",
                    direction="inbound",
                    provider_message_id="provider_msg_3",
                    body_redacted="cuantos dias de vacaciones me quedan?",
                    delivery_status="received",
                    created_at=NOW - timedelta(minutes=1),
                ),
            ]
        )
        await session.commit()


@pytest.fixture()
async def world(db) -> World:
    await build_world(db)
    return World(sessions=db, ids={"location": LOCATION_ID, "manager": MANAGER_ID})


@pytest.fixture()
def app(world) -> FastAPI:
    application = create_app()

    async def override_session():
        async with world.sessions() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[get_settings] = settings_override
    return application


@pytest.fixture()
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


def auth_headers(manager_id: str = MANAGER_ID, role: str = "manager") -> dict[str, str]:
    """Bearer header from a directly-issued token (login is tested apart)."""
    from app.security.tokens import issue_token

    token, _ = issue_token(manager_id, role, TEST_SETTINGS)
    return {"Authorization": f"Bearer {token}"}
