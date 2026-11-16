"""Pulls recorded on the stat taker: hang time, where it landed, and how
it went (caught, let land, out, brick, dropped)

Revision ID: d2f4a6c8e0b1
Revises: f7b9d1c3e5a8
Create Date: 2026-11-16

"""
from alembic import op
import sqlalchemy as sa


revision = 'd2f4a6c8e0b1'
down_revision = 'f7b9d1c3e5a8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pull', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hang_time', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('landing_x', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('landing_y', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('result', sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table('pull', schema=None) as batch_op:
        batch_op.drop_column('result')
        batch_op.drop_column('landing_y')
        batch_op.drop_column('landing_x')
        batch_op.drop_column('hang_time')
