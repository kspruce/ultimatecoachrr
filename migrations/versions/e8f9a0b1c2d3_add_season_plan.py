"""Add the season plan feature: team_settings.season_plan_enabled and the
season_plan, season_phase, season_week, season_page and season_milestone tables

Revision ID: e8f9a0b1c2d3
Revises: d5e6f7a8b9c0
Create Date: 2026-10-16 14:00:00.000000

The toggle defaults to false, so no existing team sees the feature until a
coach switches it on. The new tables start empty.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e8f9a0b1c2d3'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.add_column(sa.Column('season_plan_enabled', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))

    op.create_table(
        'season_plan',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('season', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('source', sa.String(length=200), nullable=True),
        sa.Column('imported_at', sa.DateTime(), nullable=True),
        sa.Column('players_see_overview', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('players_see_weeks', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('players_see_session_notes', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('players_see_phases', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_organization_id', 'season', name='uq_season_plan_team_season'),
    )

    op.create_table(
        'season_phase',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('start_week', sa.Integer(), nullable=True),
        sa.Column('end_week', sa.Integer(), nullable=True),
        sa.Column('aim', sa.Text(), nullable=True),
        sa.Column('training_focus', sa.Text(), nullable=True),
        sa.Column('events', sa.Text(), nullable=True),
        sa.Column('classroom_refs', sa.String(length=200), nullable=True),
        sa.Column('strategic_anchor', sa.Text(), nullable=True),
        sa.Column('colour', sa.String(length=7), nullable=True),
        sa.Column('progression', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['season_plan.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plan_id', 'number', name='uq_season_phase_plan_number'),
    )
    op.create_index('ix_season_phase_plan_id', 'season_phase', ['plan_id'], unique=False)

    op.create_table(
        'season_week',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('phase_id', sa.Integer(), nullable=True),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('week_number', sa.Integer(), nullable=False),
        sa.Column('week_commencing', sa.Date(), nullable=True),
        sa.Column('block', sa.String(length=200), nullable=True),
        sa.Column('joint_theme', sa.Text(), nullable=True),
        sa.Column('firsts_theme', sa.Text(), nullable=True),
        sa.Column('seconds_theme', sa.Text(), nullable=True),
        sa.Column('classroom', sa.String(length=200), nullable=True),
        sa.Column('off_pitch', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('session_title', sa.String(length=200), nullable=True),
        sa.Column('session_detail_md', sa.Text(), nullable=True),
        sa.Column('is_event', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_break', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('session_plan_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['season_plan.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['phase_id'], ['season_phase.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_plan_id'], ['session_plan.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plan_id', 'week_number', name='uq_season_week_plan_number'),
    )
    op.create_index('ix_season_week_plan_id', 'season_week', ['plan_id'], unique=False)

    op.create_table(
        'season_page',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('body_markdown', sa.Text(), nullable=True),
        sa.Column('players_can_view', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['plan_id'], ['season_plan.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plan_id', 'slug', name='uq_season_page_plan_slug'),
    )
    op.create_index('ix_season_page_plan_id', 'season_page', ['plan_id'], unique=False)

    op.create_table(
        'season_milestone',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('when_label', sa.String(length=100), nullable=False),
        sa.Column('what', sa.Text(), nullable=False),
        sa.Column('start_week', sa.Integer(), nullable=True),
        sa.Column('end_week', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['season_plan.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_season_milestone_plan_id', 'season_milestone', ['plan_id'], unique=False)


def downgrade():
    op.drop_index('ix_season_milestone_plan_id', table_name='season_milestone')
    op.drop_table('season_milestone')
    op.drop_index('ix_season_page_plan_id', table_name='season_page')
    op.drop_table('season_page')
    op.drop_index('ix_season_week_plan_id', table_name='season_week')
    op.drop_table('season_week')
    op.drop_index('ix_season_phase_plan_id', table_name='season_phase')
    op.drop_table('season_phase')
    op.drop_table('season_plan')

    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.drop_column('season_plan_enabled')
