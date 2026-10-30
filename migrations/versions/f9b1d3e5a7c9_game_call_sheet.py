"""Game call sheet: the plays planned for a game, and the play called each point

Revision ID: f9b1d3e5a7c9
Revises: e8a0c2d4f6b8
Create Date: 2026-10-30 18:00:00.000000

- game_call_play: a game's call sheet (plays in order, with a note)
- point.called_play_id: the play called for the point (empty for every
  point recorded so far)
"""
from alembic import op
import sqlalchemy as sa


revision = 'f9b1d3e5a7c9'
down_revision = 'e8a0c2d4f6b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'game_call_play',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_organization_id', sa.Integer(), sa.ForeignKey('team_organization.id'), nullable=False),
        sa.Column('game_id', sa.Integer(), sa.ForeignKey('game.id', ondelete='CASCADE'), nullable=False),
        sa.Column('play_id', sa.Integer(), sa.ForeignKey('play.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('note', sa.String(length=120), nullable=True),
        sa.UniqueConstraint('game_id', 'play_id', name='uq_game_call_play'),
    )
    op.create_index('ix_game_call_play_team_organization_id', 'game_call_play', ['team_organization_id'])
    op.create_index('ix_game_call_play_game_id', 'game_call_play', ['game_id'])
    with op.batch_alter_table('point') as batch_op:
        batch_op.add_column(sa.Column('called_play_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_point_called_play', 'play', ['called_play_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_point_called_play_id', ['called_play_id'])


def downgrade():
    with op.batch_alter_table('point') as batch_op:
        batch_op.drop_index('ix_point_called_play_id')
        batch_op.drop_constraint('fk_point_called_play', type_='foreignkey')
        batch_op.drop_column('called_play_id')
    op.drop_index('ix_game_call_play_game_id', table_name='game_call_play')
    op.drop_index('ix_game_call_play_team_organization_id', table_name='game_call_play')
    op.drop_table('game_call_play')
