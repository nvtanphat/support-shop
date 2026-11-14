"""policy_chunk_provenance

Adds source, title, parent_id, status, content_hash and updated_at to policy_chunks so documents other
than the generated clauses can be indexed incrementally and retired without losing history.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-13 18:00:00.000000+00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("policy_chunks", sa.Column("source", sa.String(255), nullable=False, server_default="rules.yaml"))
    op.add_column("policy_chunks", sa.Column("title", sa.String(255), nullable=True))
    op.add_column("policy_chunks", sa.Column("parent_id", sa.String(64), nullable=True))
    op.add_column("policy_chunks", sa.Column("status", sa.String(16), nullable=False, server_default="active"))
    op.add_column("policy_chunks", sa.Column("content_hash", sa.String(64), nullable=False, server_default=""))
    op.add_column(
        "policy_chunks",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_policy_chunks_parent_id", "policy_chunks", ["parent_id"])
    op.create_index("ix_policy_chunks_status", "policy_chunks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_policy_chunks_status", table_name="policy_chunks")
    op.drop_index("ix_policy_chunks_parent_id", table_name="policy_chunks")
    for column in ("updated_at", "content_hash", "status", "parent_id", "title", "source"):
        op.drop_column("policy_chunks", column)
