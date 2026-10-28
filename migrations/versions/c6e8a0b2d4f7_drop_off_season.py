"""Drop the off-season tables

Revision ID: c6e8a0b2d4f7
Revises: c6e8a0b2d4f6
Create Date: 2026-10-24 12:00:00.000000

Programmes replaced the off-season section (phases, schedules, workouts,
SMART goals and the track workout plan), which had no way in from the menu.
Its tables and whatever was in them go. They were made by create_all rather
than a migration, so IF EXISTS covers databases that never had them, and the
downgrade doesn't bring them back.
"""
from alembic import op


revision = 'c6e8a0b2d4f7'
down_revision = 'c6e8a0b2d4f6'
branch_labels = None
depends_on = None


# Children before the tables they point at
TABLES = [
    'user_session_completions',
    'session_workout_plans',
    'workout_plans',
    'schedule_sessions',
    'phase_schedules',
    'phase_metrics',
    'user_schedule_preferences',
    'smart_goals',
    'off_season_phases',
    'track_workout_weeks',
]


def upgrade():
    for table in TABLES:
        op.execute(f'DROP TABLE IF EXISTS {table}')


def downgrade():
    pass
