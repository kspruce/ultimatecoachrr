"""Add pull hang_time fields

Revision ID: f1a2b3c4d5e6
Revises: e3e44e60d100
Create Date: 2026-03-23 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = '7116f57dd6ec'
branch_labels = None
depends_on = None


def upgrade():
    # Add hang_time to game_day_event (nullable float, seconds in air)
    op.add_column('game_day_event',
        sa.Column('hang_time', sa.Float(), nullable=True)
    )
    # Add total_hang_time to game_day_player_stats (cumulative hang time per player per game)
    op.add_column('game_day_player_stats',
        sa.Column('total_hang_time', sa.Float(), nullable=True, server_default='0.0')
    )


def downgrade():
    op.drop_column('game_day_player_stats', 'total_hang_time')
    op.drop_column('game_day_event', 'hang_time')
