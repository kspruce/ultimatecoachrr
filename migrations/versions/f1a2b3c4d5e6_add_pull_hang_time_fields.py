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
    # Use raw SQL with IF NOT EXISTS so the migration is safe to run even if
    # the columns were added directly to the database outside of Alembic.
    op.execute("ALTER TABLE game_day_event ADD COLUMN IF NOT EXISTS hang_time FLOAT")
    op.execute("ALTER TABLE game_day_player_stats ADD COLUMN IF NOT EXISTS total_hang_time FLOAT DEFAULT 0.0")


def downgrade():
    op.drop_column('game_day_player_stats', 'total_hang_time')
    op.drop_column('game_day_event', 'hang_time')
