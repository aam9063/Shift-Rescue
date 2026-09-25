"""audit events may belong to no rescue (system-level events)

Revision ID: 0004_audit_nullable_rescue
Revises: 0003_manager_locations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_audit_nullable_rescue"
down_revision: str | None = "0003_manager_locations"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("audit_event", "rescue_id", existing_type=sa.String(64), nullable=True)


def downgrade() -> None:
    op.alter_column("audit_event", "rescue_id", existing_type=sa.String(64), nullable=False)
