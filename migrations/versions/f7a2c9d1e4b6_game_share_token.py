"""Game summaries can be shared with a link

Revision ID: f7a2c9d1e4b6
Revises: e4f1b2c3d5a7
Create Date: 2026-11-10

"""
from alembic import op
import sqlalchemy as sa


revision = 'f7a2c9d1e4b6'
down_revision = 'e4f1b2c3d5a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game', schema=None) as batch_op:
        batch_op.add_column(sa.Column('share_token', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_game_share_token', ['share_token'], unique=True)


def downgrade():
    with op.batch_alter_table('game', schema=None) as batch_op:
        batch_op.drop_index('ix_game_share_token')
        batch_op.drop_column('share_token')
