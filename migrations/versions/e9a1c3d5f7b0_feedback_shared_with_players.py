"""Coach feedback can be shared with the player, and linked to a game or clip

Revision ID: e9a1c3d5f7b0
Revises: d8f0b2c4e6a9
Create Date: 2026-10-24 13:00:00.000000

The player page had its own notes box (player.coach_feedback, entries split
by '---' with an optional "[16 Mar 2026]" date) that the player could read.
Each entry becomes a shared feedback note, so it shows in the same place as
the rest, and the box's column goes. The downgrade brings the column back
empty: the notes stay as feedback.
"""
from datetime import datetime, timedelta

from alembic import op
import sqlalchemy as sa


revision = 'e9a1c3d5f7b0'
down_revision = 'd8f0b2c4e6a9'
branch_labels = None
depends_on = None


def notes_box_entries(text):
    """[(date or None, content)] from an old notes box, newest first."""
    entries = []
    for chunk in (text or '').split('---'):
        chunk = chunk.strip()
        if not chunk:
            continue
        when = None
        if chunk.startswith('[') and ']' in chunk:
            label, rest = chunk[1:chunk.index(']')].strip(), chunk[chunk.index(']') + 1:].strip()
            for fmt in ('%d %b %Y', '%d %B %Y', '%Y-%m-%d', '%d/%m/%Y'):
                try:
                    when = datetime.strptime(label, fmt)
                except ValueError:
                    continue
                chunk = rest or chunk
                break
        entries.append((when, chunk))
    return entries


def upgrade():
    with op.batch_alter_table('player_feedback') as batch_op:
        batch_op.alter_column('coach_id', existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column('game_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('clip_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('shared', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('seen_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key('fk_player_feedback_game', 'game', ['game_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_player_feedback_clip', 'clip', ['clip_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_player_feedback_game_id', ['game_id'])
        batch_op.create_index('ix_player_feedback_clip_id', ['clip_id'])

    bind = op.get_bind()
    player = sa.table('player', sa.column('id'), sa.column('coach_feedback'))
    feedback = sa.table('player_feedback', sa.column('player_id'), sa.column('content'),
                        sa.column('context_tag'), sa.column('shared'), sa.column('created_at'))
    rows = bind.execute(sa.select(player.c.id, player.c.coach_feedback)
                        .where(player.c.coach_feedback.isnot(None))).fetchall()
    now = datetime.utcnow().replace(microsecond=0)
    for player_id, text in rows:
        newer = now
        for when, content in notes_box_entries(text):
            # An undated entry goes just before the one above it in the box
            newer = when or newer - timedelta(seconds=1)
            bind.execute(feedback.insert().values(
                player_id=player_id, content=content, context_tag='General', shared=True,
                created_at=newer))
    with op.batch_alter_table('player') as batch_op:
        batch_op.drop_column('coach_feedback')


def downgrade():
    with op.batch_alter_table('player') as batch_op:
        batch_op.add_column(sa.Column('coach_feedback', sa.Text(), nullable=True))
    with op.batch_alter_table('player_feedback') as batch_op:
        batch_op.drop_index('ix_player_feedback_clip_id')
        batch_op.drop_index('ix_player_feedback_game_id')
        batch_op.drop_constraint('fk_player_feedback_clip', type_='foreignkey')
        batch_op.drop_constraint('fk_player_feedback_game', type_='foreignkey')
        batch_op.drop_column('seen_at')
        batch_op.drop_column('shared')
        batch_op.drop_column('clip_id')
        batch_op.drop_column('game_id')
