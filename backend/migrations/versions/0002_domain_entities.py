"""domain rules: all spec §4.1 entity tables

Revision ID: 0002_domain_entities
Revises: 0001_foundation
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_domain_entities"
down_revision: str | None = "0001_foundation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _timestamp_column() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "employee",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("location_id", sa.String(64), nullable=False, index=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("phone_e164", sa.String(20), nullable=False, unique=True),
        sa.Column("language", sa.String(5), nullable=False, server_default="es"),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("contract_weekly_hours", sa.Integer(), nullable=False),
        sa.Column("max_weekly_hours", sa.Integer(), nullable=False),
        sa.Column("home_zone", sa.String(80), nullable=False),
        sa.Column("accepts_extra_shifts", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _timestamp_column(),
    )
    op.create_table(
        "shift",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("location_id", sa.String(64), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("employee_id", sa.String(64), nullable=True, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        _timestamp_column(),
    )
    op.create_table(
        "availability_block",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("employee_id", sa.String(64), nullable=False, index=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        _timestamp_column(),
    )
    op.create_table(
        "rescue_case",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("location_id", sa.String(64), nullable=False, index=True),
        sa.Column("shift_id", sa.String(64), nullable=False, index=True),
        sa.Column("absent_employee_id", sa.String(64), nullable=False),
        sa.Column("origin", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(40), nullable=True),
        sa.Column("covering_employee_id", sa.String(64), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"),
        _timestamp_column(),
    )
    op.create_table(
        "offer",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("rescue_id", sa.String(64), nullable=False, index=True),
        sa.Column("employee_id", sa.String(64), nullable=False, index=True),
        sa.Column("wave_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposed_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposed_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approval_reason", sa.String(40), nullable=True),
        _timestamp_column(),
    )
    op.create_table(
        "conversation",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("employee_id", sa.String(64), nullable=True, index=True),
        sa.Column("manager_id", sa.String(64), nullable=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp_column(),
    )
    op.create_table(
        "message",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("conversation_id", sa.String(64), nullable=False, index=True),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("provider_message_id", sa.String(80), nullable=False),
        sa.Column("body_redacted", sa.Text(), nullable=False),
        sa.Column("template_key", sa.String(60), nullable=True),
        sa.Column("delivery_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("rescue_id", sa.String(64), nullable=True, index=True),
        _timestamp_column(),
        sa.UniqueConstraint("provider_message_id", name="uq_message_provider_id"),
    )
    op.create_table(
        "interpretation",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("message_id", sa.String(64), nullable=False, index=True),
        sa.Column("intent", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extracted", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(30), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        _timestamp_column(),
    )
    op.create_table(
        "approval_request",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("rescue_id", sa.String(64), nullable=False, index=True),
        sa.Column("offer_id", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.String(64), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp_column(),
    )
    op.create_table(
        "audit_event",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("rescue_id", sa.String(64), nullable=False, index=True),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("actor", sa.String(60), nullable=False, server_default="system"),
        _timestamp_column(),
    )
    op.create_table(
        "eval_run",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("git_sha", sa.String(40), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("prompt_versions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("invariant_violations", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("baseline_run_id", sa.String(64), nullable=True),
        sa.Column("report_path", sa.String(200), nullable=True),
        _timestamp_column(),
    )
    op.create_table(
        "location_settings",
        sa.Column("location_id", sa.String(64), primary_key=True),
        sa.Column("wave_size", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("wave_interval_minutes", sa.Integer(), nullable=False, server_default="10"),
        sa.Column(
            "rescue_deadline_minutes_before_start",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        sa.Column("min_rest_hours", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("max_coverages_per_14_days", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("quiet_hours_start", sa.String(5), nullable=False, server_default="23:00"),
        sa.Column("quiet_hours_end", sa.String(5), nullable=False, server_default="07:00"),
        sa.Column("ranking_weights", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("agent_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        _timestamp_column(),
    )


def downgrade() -> None:
    for table in (
        "location_settings",
        "eval_run",
        "audit_event",
        "approval_request",
        "interpretation",
        "message",
        "conversation",
        "offer",
        "rescue_case",
        "availability_block",
        "shift",
        "employee",
    ):
        op.drop_table(table)
