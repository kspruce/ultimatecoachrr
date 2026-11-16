"""New players pick a provisional shirt number

Revision ID: e5a7c9b1d3f6
Revises: d4f6b8a0c2e4
Create Date: 2026-11-16

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5a7c9b1d3f6'
down_revision = 'd4f6b8a0c2e4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.add_column(sa.Column('number_provisional', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.drop_column('number_provisional')
