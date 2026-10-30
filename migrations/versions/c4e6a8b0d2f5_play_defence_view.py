"""How a play's drawing shows the defence

Revision ID: c4e6a8b0d2f5
Revises: b3d5f7a9c1e3
Create Date: 2026-10-30 12:00:00.000000

- play.defence_view: show, faded or hidden. Where the animation starts on
  the play's page and in previews; empty means shown.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c4e6a8b0d2f5'
down_revision = 'b3d5f7a9c1e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('play') as batch_op:
        batch_op.add_column(sa.Column('defence_view', sa.String(length=10), nullable=True))


def downgrade():
    with op.batch_alter_table('play') as batch_op:
        batch_op.drop_column('defence_view')
