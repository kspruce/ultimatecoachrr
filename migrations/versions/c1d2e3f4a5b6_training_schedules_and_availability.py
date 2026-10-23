"""Training schedules, availability, session templates, reminders and the
new Discord setup

Revision ID: c1d2e3f4a5b6
Revises: e9f0a1b2c3d4
Create Date: 2026-10-23

- training_schedule (+ training_schedule_squad): regular sessions whose
  dates are made ahead as session_plan rows (session_plan.schedule_id).
- session_plan: which squads it's for (session_plan_squad, filled from the
  season plan's 1s / 2s label where the team has squads by those names),
  status (scheduled / cancelled), cancel_reason and is_published. The
  never-used is_recurring and recurrence_pattern go.
- schedule_availability: players' usual answers per schedule.
- session_template and session_reminder.
- session_rsvp: answers saved from Discord as yes / no become attending /
  not_attending and get their team; duplicates (one player answering one
  session twice) keep the newest; then one answer per player per session.
- team_settings: what players see, reminders, the connected Discord server
  and weekly post. The per-team bot token and calendar sync settings (never
  used) go.
- user.discord_username.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c1d2e3f4a5b6'
down_revision = 'e9f0a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'training_schedule',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('weekday', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=True),
        sa.Column('end_time', sa.Time(), nullable=True),
        sa.Column('location', sa.String(length=100), nullable=True),
        sa.Column('session_type', sa.String(length=20), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('others_welcome', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_training_schedule_team_organization_id', 'training_schedule', ['team_organization_id'])

    op.create_table(
        'training_schedule_squad',
        sa.Column('schedule_id', sa.Integer(), nullable=False),
        sa.Column('squad_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['schedule_id'], ['training_schedule.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['squad_id'], ['squad.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('schedule_id', 'squad_id'),
    )

    with op.batch_alter_table('session_plan') as batch_op:
        batch_op.add_column(sa.Column('schedule_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('status', sa.String(length=20), nullable=False, server_default='scheduled'))
        batch_op.add_column(sa.Column('cancel_reason', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.create_foreign_key('fk_session_plan_schedule_id', 'training_schedule', ['schedule_id'], ['id'],
                                    ondelete='SET NULL')
        batch_op.create_index('ix_session_plan_schedule_id', ['schedule_id'])
        batch_op.drop_column('is_recurring')
        batch_op.drop_column('recurrence_pattern')

    op.create_table(
        'session_plan_squad',
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('squad_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['session_plan.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['squad_id'], ['squad.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('session_id', 'squad_id'),
    )
    op.execute("""
        INSERT INTO session_plan_squad (session_id, squad_id)
        SELECT sp.id, sq.id FROM session_plan sp
        JOIN squad sq ON sq.team_organization_id = sp.team_organization_id AND lower(sq.name) = sp.squad
        WHERE sp.squad IN ('1s', '2s')
    """)

    op.create_table(
        'schedule_availability',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('schedule_id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['schedule_id'], ['training_schedule.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('schedule_id', 'player_id', name='uq_schedule_availability_player'),
    )
    op.create_index('ix_schedule_availability_schedule_id', 'schedule_availability', ['schedule_id'])
    op.create_index('ix_schedule_availability_player_id', 'schedule_availability', ['player_id'])

    op.create_table(
        'session_template',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('blocks', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_session_template_team_organization_id', 'session_template', ['team_organization_id'])

    op.create_table(
        'session_reminder',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('team_organization_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['session_plan.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'player_id', 'kind', name='uq_session_reminder'),
    )
    op.create_index('ix_session_reminder_session_id', 'session_reminder', ['session_id'])

    # Answers: one vocabulary, their team, one per player per session
    op.execute("UPDATE session_rsvp SET status = 'attending' WHERE status = 'yes'")
    op.execute("UPDATE session_rsvp SET status = 'not_attending' WHERE status = 'no'")
    op.execute("""
        UPDATE session_rsvp SET team_organization_id = (
            SELECT sp.team_organization_id FROM session_plan sp WHERE sp.id = session_rsvp.session_id)
        WHERE team_organization_id IS NULL
    """)
    op.execute("""
        DELETE FROM session_rsvp WHERE id NOT IN (
            SELECT keep FROM (SELECT max(id) AS keep FROM session_rsvp GROUP BY session_id, player_id) AS newest)
    """)
    with op.batch_alter_table('session_rsvp') as batch_op:
        batch_op.create_unique_constraint('uq_session_rsvp_player', ['session_id', 'player_id'])

    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.add_column(sa.Column('discord_guild_name', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('discord_week_post_day', sa.Integer(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('discord_week_posted_on', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('attendee_visibility', sa.String(length=10), nullable=False,
                                      server_default='names'))
        batch_op.add_column(sa.Column('plan_visible_days', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reminders_enabled', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('reminder_days', sa.Integer(), nullable=False, server_default='7'))
        batch_op.drop_column('discord_bot_token')
        batch_op.drop_column('discord_calendar_channel_id')
        batch_op.drop_column('discord_sync_calendar')

    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('discord_username', sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('discord_username')

    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.add_column(sa.Column('discord_sync_calendar', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('discord_calendar_channel_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('discord_bot_token', sa.String(length=255), nullable=True))
        for column in ('reminder_days', 'reminders_enabled', 'plan_visible_days', 'attendee_visibility',
                       'discord_week_posted_on', 'discord_week_post_day', 'discord_guild_name'):
            batch_op.drop_column(column)

    with op.batch_alter_table('session_rsvp') as batch_op:
        batch_op.drop_constraint('uq_session_rsvp_player', type_='unique')

    op.drop_index('ix_session_reminder_session_id', table_name='session_reminder')
    op.drop_table('session_reminder')
    op.drop_index('ix_session_template_team_organization_id', table_name='session_template')
    op.drop_table('session_template')
    op.drop_index('ix_schedule_availability_player_id', table_name='schedule_availability')
    op.drop_index('ix_schedule_availability_schedule_id', table_name='schedule_availability')
    op.drop_table('schedule_availability')
    op.drop_table('session_plan_squad')

    with op.batch_alter_table('session_plan') as batch_op:
        batch_op.add_column(sa.Column('recurrence_pattern', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('is_recurring', sa.Boolean(), nullable=True))
        batch_op.drop_index('ix_session_plan_schedule_id')
        if op.get_bind().dialect.name != 'sqlite':  # SQLite rebuilds the table without it
            batch_op.drop_constraint('fk_session_plan_schedule_id', type_='foreignkey')
        for column in ('is_published', 'cancel_reason', 'status', 'schedule_id'):
            batch_op.drop_column(column)

    op.drop_table('training_schedule_squad')
    op.drop_index('ix_training_schedule_team_organization_id', table_name='training_schedule')
    op.drop_table('training_schedule')
