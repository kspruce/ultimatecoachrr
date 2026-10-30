"""Playbook: set-ups, core plays, situations, share links, learning for a tournament

Revision ID: e8a0c2d4f6b8
Revises: d7f9b1c3e5a7
Create Date: 2026-10-30 12:00:00.000000

- play_setup: starting positions saved from the drawing editor
- play.is_core (false), play.situations, play.share_token (none yet)
- play_to_learn.tournament_id: the tournament a play is to be learned for
"""
from alembic import op
import sqlalchemy as sa


revision = 'e8a0c2d4f6b8'
down_revision = 'd7f9b1c3e5a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'play_setup',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_organization_id', sa.Integer(), sa.ForeignKey('team_organization.id'), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=True),
        sa.Column('state_json', sa.Text(), nullable=False),
        sa.Column('image_data', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_play_setup_team_organization_id', 'play_setup', ['team_organization_id'])

    with op.batch_alter_table('play') as batch_op:
        batch_op.add_column(sa.Column('is_core', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('situations', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('share_token', sa.String(length=43), nullable=True))
        batch_op.create_unique_constraint('uq_play_share_token', ['share_token'])

    with op.batch_alter_table('play_to_learn') as batch_op:
        batch_op.add_column(sa.Column('tournament_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_play_to_learn_tournament', 'tournament', ['tournament_id'], ['id'],
                                    ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('play_to_learn') as batch_op:
        batch_op.drop_constraint('fk_play_to_learn_tournament', type_='foreignkey')
        batch_op.drop_column('tournament_id')
    with op.batch_alter_table('play') as batch_op:
        batch_op.drop_constraint('uq_play_share_token', type_='unique')
        batch_op.drop_column('share_token')
        batch_op.drop_column('situations')
        batch_op.drop_column('is_core')
    op.drop_index('ix_play_setup_team_organization_id', table_name='play_setup')
    op.drop_table('play_setup')
