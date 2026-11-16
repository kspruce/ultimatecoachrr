"""Players ask to be linked to a profile; a coach approves

Revision ID: c3e5a7b9d1f2
Revises: b5d8f1a3c6e9
Create Date: 2026-11-16

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3e5a7b9d1f2'
down_revision = 'b5d8f1a3c6e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'player_link_request',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_organization_id', 'user_id', name='uq_link_request_team_user'),
    )
    op.create_index('ix_player_link_request_team_organization_id', 'player_link_request',
                    ['team_organization_id'])


def downgrade():
    op.drop_index('ix_player_link_request_team_organization_id', table_name='player_link_request')
    op.drop_table('player_link_request')
