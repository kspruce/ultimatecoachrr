"""Feedback: keep doing / work on, player replies, and "keep in mind"

Revision ID: a2c4e6f8b0d2
Revises: f9b1d3e5a7c9
Create Date: 2026-10-31 12:00:00.000000

- player_feedback.kind: note (every existing note), keep (keep doing) or
  work_on (work on)
- feedback_reply: replies on a note, from the player or a coach
- player_focus: what a player should keep in mind at the next training or
  tournament (the active one is current; earlier ones stay as history)
"""
from alembic import op
import sqlalchemy as sa


revision = 'a2c4e6f8b0d2'
down_revision = 'f9b1d3e5a7c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('player_feedback') as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(length=10), nullable=False, server_default='note'))

    op.create_table(
        'feedback_reply',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('feedback_id', sa.Integer(), sa.ForeignKey('player_feedback.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('from_player', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('seen_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_feedback_reply_feedback_id', 'feedback_reply', ['feedback_id'])

    op.create_table(
        'player_focus',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_organization_id', sa.Integer(), sa.ForeignKey('team_organization.id'), nullable=False),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('player.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('session_plan.id', ondelete='SET NULL'), nullable=True),
        sa.Column('tournament_id', sa.Integer(), sa.ForeignKey('tournament.id', ondelete='SET NULL'), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('set_by', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('seen_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_player_focus_team_organization_id', 'player_focus', ['team_organization_id'])
    op.create_index('ix_player_focus_player_id', 'player_focus', ['player_id'])


def downgrade():
    op.drop_index('ix_player_focus_player_id', table_name='player_focus')
    op.drop_index('ix_player_focus_team_organization_id', table_name='player_focus')
    op.drop_table('player_focus')
    op.drop_index('ix_feedback_reply_feedback_id', table_name='feedback_reply')
    op.drop_table('feedback_reply')
    with op.batch_alter_table('player_feedback') as batch_op:
        batch_op.drop_column('kind')
