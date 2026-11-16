"""A team's message for new players, in invite emails

Revision ID: d4f6b8a0c2e4
Revises: c3e5a7b9d1f2
Create Date: 2026-11-16

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4f6b8a0c2e4'
down_revision = 'c3e5a7b9d1f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('team_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('invite_message', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('team_settings', schema=None) as batch_op:
        batch_op.drop_column('invite_message')
