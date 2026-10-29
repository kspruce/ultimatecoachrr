"""Fill in each throw's opponent

Revision ID: b2d4f6a8c0e3
Revises: a1c3e5f7b9d2
Create Date: 2026-10-28 12:00:00.000000

Throw.opposition_team was never filled in, so filtering player connections
by opponent never matched. New throws get it when saved; this fills in the
old ones from their point's game. Data only, so the downgrade leaves it.
"""
from alembic import op


revision = 'b2d4f6a8c0e3'
down_revision = 'a1c3e5f7b9d2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE throw SET opposition_team = (
            SELECT SUBSTR(g.opponent, 1, 50) FROM point p JOIN game g ON g.id = p.game_id
            WHERE p.id = throw.point_id)
        WHERE opposition_team IS NULL
    """)


def downgrade():
    pass
