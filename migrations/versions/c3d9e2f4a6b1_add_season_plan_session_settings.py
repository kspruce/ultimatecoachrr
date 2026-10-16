"""Add the settings for building sessions from the season plan: training
day, times and location for joint and split sessions, and when sessions
were last built

Revision ID: c3d9e2f4a6b1
Revises: a2b3c4d5e6f7
Create Date: 2026-10-16 18:00:00.000000

All columns are nullable and start empty, so nothing changes until a coach
builds sessions from Season plan > Sessions.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d9e2f4a6b1'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('season_plan') as batch_op:
        batch_op.add_column(sa.Column('joint_weekday', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('joint_start', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('joint_end', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('split_weekday', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('split_start', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('split_end', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('session_location', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('sessions_built_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('season_plan') as batch_op:
        for name in ('sessions_built_at', 'session_location', 'split_end', 'split_start',
                     'split_weekday', 'joint_end', 'joint_start', 'joint_weekday'):
            batch_op.drop_column(name)
