"""Coaches' debrief on a game: what worked, what didn't, what to train

Revision ID: e9a3c1d5f7b4
Revises: d8f2b0c4e6a3
Create Date: 2026-11-12

"""
from alembic import op
import sqlalchemy as sa


revision = 'e9a3c1d5f7b4'
down_revision = 'd8f2b0c4e6a3'
branch_labels = None
depends_on = None

COLUMNS = ('debrief_worked', 'debrief_improve', 'debrief_train')


def upgrade():
    with op.batch_alter_table('game', schema=None) as batch_op:
        for name in COLUMNS:
            batch_op.add_column(sa.Column(name, sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('game', schema=None) as batch_op:
        for name in COLUMNS:
            batch_op.drop_column(name)
