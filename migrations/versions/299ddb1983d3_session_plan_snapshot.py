"""Remember what the season plan last wrote to each built session

Revision ID: 299ddb1983d3
Revises: b8d0f2a4c6e8
Create Date: 2026-11-17

session_plan.plan_snapshot holds a fingerprint of each part of a session
(blocks, title, focus, aim, learning points, notes, when) as the season
plan last wrote it, so building again can tell a coach's edit from the
plan's and keep the coach's (app/utils/season_sessions.py).
"""
from alembic import op
import sqlalchemy as sa


revision = '299ddb1983d3'
down_revision = 'b8d0f2a4c6e8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('session_plan') as batch:
        batch.add_column(sa.Column('plan_snapshot', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('session_plan') as batch:
        batch.drop_column('plan_snapshot')
