"""Tournament reply-by dates and selection, game times, calendar feeds

Revision ID: a3c5e7f9b1d2
Revises: e9f0a1b2c3d4
Create Date: 2026-10-23 18:00:00.000000

- tournament: notes, rsvp_deadline, squad_size_target, selection_published,
  reminder_sent_at
- tournament_rsvp: status may be empty (picked before replying), the
  coach's selection (picked / reserve / not_picked) and when the player
  answered. Existing admin selections become 'picked' (picks of players who
  never replied lose the made-up "attending"), and tournaments that
  already had selections are marked published so players still see them.
- game: start_time and field
- player: line_preference (dropped in 7729e5ca9089 but still used)
- user: calendar_token and email_event_updates
"""
from alembic import op
import sqlalchemy as sa


revision = 'a3c5e7f9b1d2'
down_revision = 'e9f0a1b2c3d4'
branch_labels = None
depends_on = None


def _columns(table):
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    with op.batch_alter_table('tournament') as batch_op:
        batch_op.add_column(sa.Column('notes', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('rsvp_deadline', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('squad_size_target', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('selection_published', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column('reminder_sent_at', sa.DateTime(), nullable=True))

    with op.batch_alter_table('tournament_rsvp') as batch_op:
        batch_op.alter_column('status', existing_type=sa.String(length=20), nullable=True)
        batch_op.add_column(sa.Column('selection', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('responded_at', sa.DateTime(), nullable=True))

    with op.batch_alter_table('game') as batch_op:
        batch_op.add_column(sa.Column('start_time', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('field', sa.String(length=50), nullable=True))

    if 'line_preference' not in _columns('player'):
        with op.batch_alter_table('player') as batch_op:
            batch_op.add_column(sa.Column('line_preference', sa.String(length=20), nullable=True))

    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('calendar_token', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('email_event_updates', sa.Boolean(), nullable=False,
                                      server_default=sa.true()))
        batch_op.create_unique_constraint('uq_user_calendar_token', ['calendar_token'])

    # Existing data: admin selections become picks, replies count as answered
    op.execute("UPDATE tournament_rsvp SET selection = 'picked' WHERE selected_by_admin")
    op.execute("UPDATE tournament_rsvp SET responded_at = COALESCE(updated_at, created_at) "
               "WHERE notes IS NULL OR notes <> 'Added by admin'")
    # Rows the coach made by picking someone who never replied weren't the
    # player's answer: they become "no reply"
    op.execute("UPDATE tournament_rsvp SET status = NULL, notes = NULL WHERE notes = 'Added by admin'")
    op.execute("UPDATE tournament SET selection_published = true WHERE id IN "
               "(SELECT tournament_id FROM tournament_rsvp WHERE selected_by_admin)")


def downgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_constraint('uq_user_calendar_token', type_='unique')
        batch_op.drop_column('email_event_updates')
        batch_op.drop_column('calendar_token')
    with op.batch_alter_table('player') as batch_op:
        batch_op.drop_column('line_preference')
    with op.batch_alter_table('game') as batch_op:
        batch_op.drop_column('field')
        batch_op.drop_column('start_time')
    op.execute("UPDATE tournament_rsvp SET status = 'attending' WHERE status IS NULL")
    with op.batch_alter_table('tournament_rsvp') as batch_op:
        batch_op.drop_column('responded_at')
        batch_op.drop_column('selection')
        batch_op.alter_column('status', existing_type=sa.String(length=20), nullable=False)
    with op.batch_alter_table('tournament') as batch_op:
        batch_op.drop_column('reminder_sent_at')
        batch_op.drop_column('selection_published')
        batch_op.drop_column('squad_size_target')
        batch_op.drop_column('rsvp_deadline')
        batch_op.drop_column('notes')
