"""Add halftime scores to game

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-03-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game', schema=None) as batch_op:
        batch_op.add_column(sa.Column('halftime_our_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('halftime_their_score', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('game', schema=None) as batch_op:
        batch_op.drop_column('halftime_their_score')
        batch_op.drop_column('halftime_our_score')
