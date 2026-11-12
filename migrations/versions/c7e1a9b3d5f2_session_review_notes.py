"""Coaches' "how it went" note on a session

Revision ID: c7e1a9b3d5f2
Revises: f7a2c9d1e4b6
Create Date: 2026-11-12

"""
from alembic import op
import sqlalchemy as sa


revision = 'c7e1a9b3d5f2'
down_revision = 'f7a2c9d1e4b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('session_plan', schema=None) as batch_op:
        batch_op.add_column(sa.Column('review_notes', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('session_plan', schema=None) as batch_op:
        batch_op.drop_column('review_notes')
