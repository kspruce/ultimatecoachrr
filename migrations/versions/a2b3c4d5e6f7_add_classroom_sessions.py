"""Add classroom sessions and their resources to the season plan

Revision ID: a2b3c4d5e6f7
Revises: f0a1b2c3d4e5
Create Date: 2026-10-16 16:00:00.000000

Adds season_plan.players_see_classroom (false, so players see nothing new
until a coach opens it) and the classroom_session and classroom_resource
tables, which start empty.
"""
from alembic import op
import sqlalchemy as sa


revision = 'a2b3c4d5e6f7'
down_revision = 'f0a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('season_plan') as batch_op:
        batch_op.add_column(sa.Column('players_see_classroom', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))

    op.create_table(
        'classroom_session',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('week_id', sa.Integer(), nullable=True),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('format', sa.String(length=100), nullable=True),
        sa.Column('audience', sa.String(length=200), nullable=True),
        sa.Column('main_source', sa.String(length=200), nullable=True),
        sa.Column('goal', sa.Text(), nullable=True),
        sa.Column('starts_at', sa.DateTime(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('join_url', sa.String(length=500), nullable=True),
        sa.Column('plan_md', sa.Text(), nullable=True),
        sa.Column('prep_md', sa.Text(), nullable=True),
        sa.Column('summary_md', sa.Text(), nullable=True),
        sa.Column('commitments_md', sa.Text(), nullable=True),
        sa.Column('summary_published', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['season_plan.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['week_id'], ['season_week.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plan_id', 'code', name='uq_classroom_session_plan_code'),
    )
    op.create_index('ix_classroom_session_plan_id', 'classroom_session', ['plan_id'], unique=False)

    op.create_table(
        'classroom_resource',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('coaches_only', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['classroom_session.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_classroom_resource_session_id', 'classroom_resource', ['session_id'], unique=False)


def downgrade():
    op.drop_index('ix_classroom_resource_session_id', table_name='classroom_resource')
    op.drop_table('classroom_resource')
    op.drop_index('ix_classroom_session_plan_id', table_name='classroom_session')
    op.drop_table('classroom_session')

    with op.batch_alter_table('season_plan') as batch_op:
        batch_op.drop_column('players_see_classroom')
