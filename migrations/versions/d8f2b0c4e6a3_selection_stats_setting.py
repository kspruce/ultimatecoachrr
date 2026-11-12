"""Teams can show attendance and stats on the squad selection table

Revision ID: d8f2b0c4e6a3
Revises: c7e1a9b3d5f2
Create Date: 2026-11-12

"""
from alembic import op
import sqlalchemy as sa


revision = 'd8f2b0c4e6a3'
down_revision = 'c7e1a9b3d5f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('team_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('selection_stats_enabled', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('team_settings', schema=None) as batch_op:
        batch_op.drop_column('selection_stats_enabled')
