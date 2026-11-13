"""add_message_seq_and_constraints

Revision ID: c1a2b3c4d5e6
Revises: 182bcc2897e0
Create Date: 2026-11-12 10:30:00.000000+00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1a2b3c4d5e6'
down_revision: str | None = '182bcc2897e0'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('conversations', sa.Column('last_message_seq', sa.Integer(), nullable=False, server_default='0'))
    # batch mode so the migration also runs on SQLite (local development), which cannot ALTER constraints
    with op.batch_alter_table('messages') as batch:
        batch.create_unique_constraint('uq_message_conv_seq', ['conversation_id', 'seq'])


def downgrade() -> None:
    with op.batch_alter_table('messages') as batch:
        batch.drop_constraint('uq_message_conv_seq', type_='unique')
    op.drop_column('conversations', 'last_message_seq')
