"""manager locations: add manager.location_ids JSON column

Revision ID: 0003_manager_locations
Revises: 0002_domain_entities
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_manager_locations"
down_revision: str | None = "0002_domain_entities"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "manager",
        sa.Column("location_ids", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("manager", "location_ids")
