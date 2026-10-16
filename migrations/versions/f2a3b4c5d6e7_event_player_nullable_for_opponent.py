"""event.player_id and throw.thrower_id nullable for opponent/unknown plays

Revision ID: f2a3b4c5d6e7
Revises: c3d9e2f4a6b1
Create Date: 2026-10-16

Plays recorded as "Opponent" or "Unknown" in Positional Analysis have no
player of ours. Opponent events used to be saved with the first player on
the line as a placeholder, so that player was credited with the opponent's
plays; those placeholders are cleared here, along with the player on any
throw built from them.
"""
from alembic import op
import sqlalchemy as sa


revision = 'f2a3b4c5d6e7'
down_revision = 'c3d9e2f4a6b1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('event', schema=None) as batch_op:
        batch_op.alter_column('player_id', existing_type=sa.Integer(), nullable=True)
    with op.batch_alter_table('throw', schema=None) as batch_op:
        batch_op.alter_column('thrower_id', existing_type=sa.Integer(), nullable=True)

    op.execute("""
        UPDATE throw SET thrower_id = NULL
        WHERE throwing_event_id IN (SELECT id FROM event WHERE is_opponent = true)
    """)
    op.execute("""
        UPDATE throw SET receiver_id = NULL
        WHERE receiving_event_id IN (SELECT id FROM event WHERE is_opponent = true)
    """)
    op.execute("UPDATE event SET player_id = NULL WHERE is_opponent = true")


def downgrade():
    # Rows without a player can't be given one back; drop them first.
    op.execute("DELETE FROM throw WHERE thrower_id IS NULL")
    op.execute("""
        UPDATE throw SET throwing_event_id = NULL
        WHERE throwing_event_id IN (SELECT id FROM event WHERE player_id IS NULL)
    """)
    op.execute("""
        UPDATE throw SET receiving_event_id = NULL
        WHERE receiving_event_id IN (SELECT id FROM event WHERE player_id IS NULL)
    """)
    op.execute("DELETE FROM event WHERE player_id IS NULL")
    with op.batch_alter_table('throw', schema=None) as batch_op:
        batch_op.alter_column('thrower_id', existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table('event', schema=None) as batch_op:
        batch_op.alter_column('player_id', existing_type=sa.Integer(), nullable=False)
