"""policy_chunk_embedding_model

Records which model produced each chunk embedding, so the indexer re-embeds when the model changes and the
retriever never compares vectors from different models.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-13 20:00:00.000000+00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("policy_chunks", sa.Column("embedding_model", sa.String(128), nullable=False, server_default=""))
    # Vectors written before this column existed came from the hashed n-gram stand-in, not a language model.
    op.execute("UPDATE policy_chunks SET embedding = '[]'")


def downgrade() -> None:
    op.drop_column("policy_chunks", "embedding_model")
