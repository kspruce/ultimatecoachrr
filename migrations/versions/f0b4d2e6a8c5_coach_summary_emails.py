"""Opt-in summary emails for coaches

Revision ID: f0b4d2e6a8c5
Revises: e9a3c1d5f7b4
Create Date: 2026-11-12

"""
from alembic import op
import sqlalchemy as sa


revision = 'f0b4d2e6a8c5'
down_revision = 'e9a3c1d5f7b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_coach_summary', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
    with op.batch_alter_table('team_membership', schema=None) as batch_op:
        batch_op.add_column(sa.Column('summary_sent_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('summary_keys', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('team_membership', schema=None) as batch_op:
        batch_op.drop_column('summary_keys')
        batch_op.drop_column('summary_sent_at')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('email_coach_summary')
