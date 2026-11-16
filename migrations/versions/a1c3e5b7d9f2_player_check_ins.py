"""Player check-ins: self-assessment rubric, coach nudges

Revision ID: a1c3e5b7d9f2
Revises: d2f4a6c8e0b1
Create Date: 2026-11-16

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1c3e5b7d9f2'
down_revision = 'd2f4a6c8e0b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'rubric_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('section', sa.String(length=20), nullable=False),
        sa.Column('text', sa.String(length=200), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rubric_item_team_organization_id', 'rubric_item', ['team_organization_id'])

    op.create_table(
        'check_in_request',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('tournament_id', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.ForeignKeyConstraint(['tournament_id'], ['tournament.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['session_plan.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_check_in_request_team_organization_id', 'check_in_request', ['team_organization_id'])

    op.create_table(
        'self_assessment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=True),
        sa.Column('tournament_id', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=120), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('focus_item_id', sa.Integer(), nullable=True),
        sa.Column('seen_by_coach_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['request_id'], ['check_in_request.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tournament_id'], ['tournament.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['session_plan.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['focus_item_id'], ['rubric_item.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_self_assessment_team_organization_id', 'self_assessment', ['team_organization_id'])
    op.create_index('ix_self_assessment_player_id', 'self_assessment', ['player_id'])
    op.create_index('ix_self_assessment_request_id', 'self_assessment', ['request_id'])

    op.create_table(
        'self_assessment_score',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assessment_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['assessment_id'], ['self_assessment.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['rubric_item.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assessment_id', 'item_id', name='uq_self_assessment_score_item'),
    )
    op.create_index('ix_self_assessment_score_assessment_id', 'self_assessment_score', ['assessment_id'])
    op.create_index('ix_self_assessment_score_item_id', 'self_assessment_score', ['item_id'])


def downgrade():
    op.drop_index('ix_self_assessment_score_item_id', table_name='self_assessment_score')
    op.drop_index('ix_self_assessment_score_assessment_id', table_name='self_assessment_score')
    op.drop_table('self_assessment_score')
    op.drop_index('ix_self_assessment_request_id', table_name='self_assessment')
    op.drop_index('ix_self_assessment_player_id', table_name='self_assessment')
    op.drop_index('ix_self_assessment_team_organization_id', table_name='self_assessment')
    op.drop_table('self_assessment')
    op.drop_index('ix_check_in_request_team_organization_id', table_name='check_in_request')
    op.drop_table('check_in_request')
    op.drop_index('ix_rubric_item_team_organization_id', table_name='rubric_item')
    op.drop_table('rubric_item')
