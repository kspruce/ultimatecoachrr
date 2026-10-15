"""Add season plan fields to session_plan / session_component / saved_drill,
and the drill_diagram table

Revision ID: f7a8b9c0d1e2
Revises: e1f2a3b4c5d6
Create Date: 2026-10-15

All new columns are nullable (is_standard_card has a server default of false),
so existing rows are untouched. external_id is unique per team, not globally.
"""
from alembic import op
import sqlalchemy as sa


revision = 'f7a8b9c0d1e2'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('session_plan', schema=None) as batch_op:
        batch_op.add_column(sa.Column('external_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('season', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('phase_number', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('phase_name', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('block', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('week_number', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('week_commencing', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('squad', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('aim', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('learning_points', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('key_terms', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('run_by', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('kit', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('sources', sa.Text(), nullable=True))
        batch_op.create_unique_constraint(
            'uq_session_plan_team_external_id', ['team_organization_id', 'external_id'])
        batch_op.create_index(
            'ix_session_plan_team_season', ['team_organization_id', 'season'], unique=False)

    with op.batch_alter_table('session_component', schema=None) as batch_op:
        batch_op.add_column(sa.Column('coach_cue', sa.Text(), nullable=True))

    with op.batch_alter_table('saved_drill', schema=None) as batch_op:
        batch_op.add_column(sa.Column('external_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('source', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('is_standard_card', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column('card_code', sa.String(length=20), nullable=True))
        batch_op.create_unique_constraint(
            'uq_saved_drill_team_external_id', ['team_organization_id', 'external_id'])

    op.create_table(
        'drill_diagram',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('saved_drill_id', sa.Integer(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('svg_url', sa.String(length=500), nullable=True),
        sa.Column('caption', sa.String(length=255), nullable=True),
        sa.Column('step_label', sa.String(length=100), nullable=True),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('image_data', sa.Text(), nullable=True),
        sa.Column('image_mime', sa.String(length=50), nullable=True),
        sa.Column('image_hash', sa.String(length=64), nullable=True),
        sa.Column('svg_data', sa.Text(), nullable=True),
        sa.Column('svg_hash', sa.String(length=64), nullable=True),
        sa.Column('team_organization_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['saved_drill_id'], ['saved_drill.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_drill_diagram_saved_drill_id', 'drill_diagram', ['saved_drill_id'], unique=False)


def downgrade():
    op.drop_index('ix_drill_diagram_saved_drill_id', table_name='drill_diagram')
    op.drop_table('drill_diagram')

    with op.batch_alter_table('saved_drill', schema=None) as batch_op:
        batch_op.drop_constraint('uq_saved_drill_team_external_id', type_='unique')
        batch_op.drop_column('card_code')
        batch_op.drop_column('is_standard_card')
        batch_op.drop_column('source')
        batch_op.drop_column('external_id')

    with op.batch_alter_table('session_component', schema=None) as batch_op:
        batch_op.drop_column('coach_cue')

    with op.batch_alter_table('session_plan', schema=None) as batch_op:
        batch_op.drop_index('ix_session_plan_team_season')
        batch_op.drop_constraint('uq_session_plan_team_external_id', type_='unique')
        for col in ('sources', 'kit', 'run_by', 'key_terms', 'learning_points', 'aim',
                    'squad', 'week_commencing', 'week_number', 'block', 'phase_name',
                    'phase_number', 'season', 'external_id'):
            batch_op.drop_column(col)
