"""Matchups: what our players mark well and what makes theirs dangerous

Revision ID: 4df1e9017ad4
Revises: 52c437aed7f5
Create Date: 2026-10-23 14:00:00.000000

Adds player.defensive_roles (e.g. "huck_stopper,deep_d") and
opponent_player.threat_roles (e.g. "hucker,deep_threat"), both empty to
start, which the scouting matchup board pairs up.
"""
from alembic import op
import sqlalchemy as sa


revision = '4df1e9017ad4'
down_revision = '52c437aed7f5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('player') as batch_op:
        batch_op.add_column(sa.Column('defensive_roles', sa.String(length=255), nullable=True))
    with op.batch_alter_table('opponent_player') as batch_op:
        batch_op.add_column(sa.Column('threat_roles', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('opponent_player') as batch_op:
        batch_op.drop_column('threat_roles')
    with op.batch_alter_table('player') as batch_op:
        batch_op.drop_column('defensive_roles')
