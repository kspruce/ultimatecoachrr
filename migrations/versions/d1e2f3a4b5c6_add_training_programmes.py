"""Add training programmes: any club's programmes, versions, tracks, weeks,
sessions, exercises, tests, milestones, enrolments, logs and results

Revision ID: d1e2f3a4b5c6
Revises: c4d5e6f7a8b9
Create Date: 2026-10-21

New tables only, all empty; nothing existing changes.
"""
from alembic import op
import sqlalchemy as sa


revision = 'd1e2f3a4b5c6'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('programme',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uid', sa.String(length=32), nullable=False),
    sa.Column('team_organization_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('is_shared', sa.Boolean(), nullable=False),
    sa.Column('coach_notes', sa.Text(), nullable=True),
    sa.Column('schedule_mode', sa.String(length=20), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('pauses', sa.JSON(), nullable=True),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('workload_enabled', sa.Boolean(), nullable=False),
    sa.Column('recovery_enabled', sa.Boolean(), nullable=False),
    sa.Column('source_kind', sa.String(length=20), nullable=True),
    sa.Column('source_uid', sa.String(length=32), nullable=True),
    sa.Column('source_name', sa.String(length=200), nullable=True),
    sa.Column('source_team', sa.String(length=100), nullable=True),
    sa.Column('source_version', sa.Integer(), nullable=True),
    sa.Column('source_author', sa.String(length=100), nullable=True),
    sa.Column('import_filename', sa.String(length=200), nullable=True),
    sa.Column('import_hash', sa.String(length=64), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uid')
    )
    with op.batch_alter_table('programme', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_programme_import_hash'), ['import_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_programme_team_organization_id'), ['team_organization_id'], unique=False)

    op.create_table('programme_version',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('programme_id', sa.Integer(), nullable=False),
    sa.Column('team_organization_id', sa.Integer(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('change_note', sa.Text(), nullable=True),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.Column('published_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['programme_id'], ['programme.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['published_by_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('programme_id', 'number', name='uq_programme_version_number')
    )
    with op.batch_alter_table('programme_version', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_programme_version_programme_id'), ['programme_id'], unique=False)

    op.create_table('performance_test',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=32), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('team_organization_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('measurement', sa.String(length=20), nullable=False),
    sa.Column('unit', sa.String(length=20), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('aggregation', sa.String(length=20), nullable=False),
    sa.Column('higher_is_better', sa.Boolean(), nullable=False),
    sa.Column('min_value', sa.Float(), nullable=True),
    sa.Column('max_value', sa.Float(), nullable=True),
    sa.Column('instructions', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['programme_version.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('performance_test', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_performance_test_key'), ['key'], unique=False)
        batch_op.create_index(batch_op.f('ix_performance_test_version_id'), ['version_id'], unique=False)

    op.create_table('programme_enrolment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('programme_id', sa.Integer(), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('player_id', sa.Integer(), nullable=False),
    sa.Column('team_organization_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('start_offset_weeks', sa.Integer(), nullable=False),
    sa.Column('pauses', sa.JSON(), nullable=True),
    sa.Column('enrolled_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['player_id'], ['player.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['programme_id'], ['programme.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['programme_version.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('programme_id', 'player_id', name='uq_programme_enrolment_player')
    )
    with op.batch_alter_table('programme_enrolment', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_programme_enrolment_player_id'), ['player_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_programme_enrolment_programme_id'), ['programme_id'], unique=False)

    op.create_table('programme_track',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=32), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('team_organization_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('colour', sa.String(length=7), nullable=True),
    sa.Column('first_week_number', sa.Integer(), nullable=False),
    sa.Column('start_offset_weeks', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['programme_version.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('programme_track', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_programme_track_version_id'), ['version_id'], unique=False)

    op.create_table('programme_week',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=32), nullable=False),
    sa.Column('track_id', sa.Integer(), nullable=False),
    sa.Column('team_organization_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('objective', sa.Text(), nullable=True),
    sa.Column('supporting_skills', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id'], ),
    sa.ForeignKeyConstraint(['track_id'], ['programme_track.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('programme_week', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_programme_week_track_id'), ['track_id'], unique=False)

    op.create_table('programme_milestone',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=32), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('team_organization_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('week_id', sa.Integer(), nullable=True),
    sa.Column('test_keys', sa.JSON(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['programme_version.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['week_id'], ['programme_week.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('programme_milestone', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_programme_milestone_version_id'), ['version_id'], unique=False)

    op.create_table('programme_session',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=32), nullable=False),
    sa.Column('week_id', sa.Integer(), nullable=False),
    sa.Column('team_organization_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('session_type', sa.String(length=20), nullable=False),
    sa.Column('custom_type', sa.String(length=50), nullable=True),
    sa.Column('requirement', sa.String(length=20), nullable=False),
    sa.Column('alternative_group', sa.String(length=50), nullable=True),
    sa.Column('duration_minutes', sa.Integer(), nullable=True),
    sa.Column('focus', sa.Text(), nullable=True),
    sa.Column('warmup', sa.Text(), nullable=True),
    sa.Column('cooldown', sa.Text(), nullable=True),
    sa.Column('coaching_cues', sa.Text(), nullable=True),
    sa.Column('video_url', sa.String(length=500), nullable=True),
    sa.Column('attachment_url', sa.String(length=500), nullable=True),
    sa.Column('log_fields', sa.JSON(), nullable=True),
    sa.Column('custom_fields', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id'], ),
    sa.ForeignKeyConstraint(['week_id'], ['programme_week.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('programme_session', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_programme_session_key'), ['key'], unique=False)
        batch_op.create_index(batch_op.f('ix_programme_session_week_id'), ['week_id'], unique=False)

    op.create_table('programme_exercise',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=32), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('team_organization_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('block', sa.String(length=20), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('sets', sa.String(length=30), nullable=True),
    sa.Column('reps', sa.String(length=50), nullable=True),
    sa.Column('distance_m', sa.Float(), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.Column('rest', sa.String(length=100), nullable=True),
    sa.Column('intensity', sa.String(length=100), nullable=True),
    sa.Column('tempo', sa.String(length=30), nullable=True),
    sa.Column('instructions', sa.Text(), nullable=True),
    sa.Column('video_url', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['programme_session.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('programme_exercise', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_programme_exercise_session_id'), ['session_id'], unique=False)

    op.create_table('programme_session_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('enrolment_id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('session_key', sa.String(length=32), nullable=False),
    sa.Column('team_organization_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('completed_on', sa.Date(), nullable=True),
    sa.Column('duration_minutes', sa.Integer(), nullable=True),
    sa.Column('rpe', sa.Integer(), nullable=True),
    sa.Column('distance_m', sa.Float(), nullable=True),
    sa.Column('soreness', sa.Integer(), nullable=True),
    sa.Column('sleep_hours', sa.Float(), nullable=True),
    sa.Column('values', sa.JSON(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('logged_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['enrolment_id'], ['programme_enrolment.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['logged_by_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['programme_session.id'], ),
    sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('enrolment_id', 'session_key', name='uq_programme_log_session')
    )
    with op.batch_alter_table('programme_session_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_programme_session_log_enrolment_id'), ['enrolment_id'], unique=False)

    op.create_table('programme_test_result',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('enrolment_id', sa.Integer(), nullable=False),
    sa.Column('test_id', sa.Integer(), nullable=False),
    sa.Column('test_key', sa.String(length=32), nullable=False),
    sa.Column('milestone_id', sa.Integer(), nullable=True),
    sa.Column('milestone_key', sa.String(length=32), nullable=True),
    sa.Column('team_organization_id', sa.Integer(), nullable=False),
    sa.Column('attempts', sa.JSON(), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('recorded_on', sa.Date(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('recorded_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['enrolment_id'], ['programme_enrolment.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['milestone_id'], ['programme_milestone.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['recorded_by_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id'], ),
    sa.ForeignKeyConstraint(['test_id'], ['performance_test.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('programme_test_result', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_programme_test_result_enrolment_id'), ['enrolment_id'], unique=False)



def downgrade():
    with op.batch_alter_table('programme_test_result', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_programme_test_result_enrolment_id'))

    op.drop_table('programme_test_result')
    with op.batch_alter_table('programme_session_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_programme_session_log_enrolment_id'))

    op.drop_table('programme_session_log')
    with op.batch_alter_table('programme_exercise', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_programme_exercise_session_id'))

    op.drop_table('programme_exercise')
    with op.batch_alter_table('programme_session', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_programme_session_week_id'))
        batch_op.drop_index(batch_op.f('ix_programme_session_key'))

    op.drop_table('programme_session')
    with op.batch_alter_table('programme_milestone', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_programme_milestone_version_id'))

    op.drop_table('programme_milestone')
    with op.batch_alter_table('programme_week', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_programme_week_track_id'))

    op.drop_table('programme_week')
    with op.batch_alter_table('programme_track', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_programme_track_version_id'))

    op.drop_table('programme_track')
    with op.batch_alter_table('programme_enrolment', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_programme_enrolment_programme_id'))
        batch_op.drop_index(batch_op.f('ix_programme_enrolment_player_id'))

    op.drop_table('programme_enrolment')
    with op.batch_alter_table('performance_test', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_performance_test_version_id'))
        batch_op.drop_index(batch_op.f('ix_performance_test_key'))

    op.drop_table('performance_test')
    with op.batch_alter_table('programme_version', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_programme_version_programme_id'))

    op.drop_table('programme_version')
    with op.batch_alter_table('programme', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_programme_team_organization_id'))
        batch_op.drop_index(batch_op.f('ix_programme_import_hash'))

    op.drop_table('programme')
