"""approval_requested_by

Records which staff member raised an approval request so the four-eyes rule can be enforced.

Revision ID: d4e5f6a7b8c9
Revises: c1a2b3c4d5e6
Create Date: 2026-11-13 12:00:00.000000+00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c1a2b3c4d5e6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("approval_requests", sa.Column("requested_by", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("approval_requests", "requested_by")
