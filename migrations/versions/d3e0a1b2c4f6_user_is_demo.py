"""The shared demo login: user.is_demo

Revision ID: d3e0a1b2c4f6
Revises: c7e9a1b3d5f7
Create Date: 2026-11-02 15:00:00.000000

- user.is_demo: the read-only demo account (app/demo); false for everyone
  else
"""
from alembic import op
import sqlalchemy as sa


revision = 'd3e0a1b2c4f6'
down_revision = 'c7e9a1b3d5f7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('is_demo')
