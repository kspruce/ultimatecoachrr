"""make user email nullable

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-03-09

Email is no longer required — players joining via invite link and
team admins registering without an email address must be supported.
The unique constraint is preserved so duplicate emails still clash,
but NULL is allowed (and multiple NULL values are fine in Postgres).
"""
from alembic import op
import sqlalchemy as sa


revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column(
            'email',
            existing_type=sa.String(length=120),
            nullable=True
        )


def downgrade():
    # NOTE: downgrade will fail if any rows have NULL email.
    # Clear them first if needed.
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column(
            'email',
            existing_type=sa.String(length=120),
            nullable=False
        )
