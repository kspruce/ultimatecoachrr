"""Tournament games are in their tournament's season

Revision ID: b5d7f9a1c3e6
Revises: a3c5e7f9b1d2
Create Date: 2026-10-24 09:00:00.000000

A game added to a tournament used to get its season from its own date (or
the current season when it had none), so a tournament could have games in
another season: they showed when filtering by the tournament but not in the
games list for the tournament's season. Games now follow their tournament;
this moves existing ones, and gives squad-less games their tournament's
squad. Data only, so the downgrade leaves it as it is.
"""
from alembic import op


revision = 'b5d7f9a1c3e6'
down_revision = 'a3c5e7f9b1d2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE game SET season_id = (SELECT t.season_id FROM tournament t WHERE t.id = game.tournament_id)
        WHERE EXISTS (SELECT 1 FROM tournament t WHERE t.id = game.tournament_id
                      AND t.season_id IS NOT NULL
                      AND (game.season_id IS NULL OR game.season_id <> t.season_id))
    """)
    op.execute("""
        UPDATE game SET squad_id = (SELECT t.squad_id FROM tournament t WHERE t.id = game.tournament_id)
        WHERE game.squad_id IS NULL
          AND EXISTS (SELECT 1 FROM tournament t WHERE t.id = game.tournament_id AND t.squad_id IS NOT NULL)
    """)


def downgrade():
    pass
