"""add invite_token table

Revision ID: a9b8c7d6e5f4
Revises: 604817d23bd6
Create Date: 2026-03-09

"""
from alembic import op
import sqlalchemy as sa

revision = 'a9b8c7d6e5f4'
down_revision = '604817d23bd6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'invite_token',
        sa.Column('id',                   sa.Integer(),    nullable=False),
        sa.Column('token',                sa.String(64),   nullable=False),
        sa.Column('player_id',            sa.Integer(),    nullable=True),
        sa.Column('team_organization_id', sa.Integer(),    nullable=False),
        sa.Column('created_by_id',        sa.Integer(),    nullable=False),
        sa.Column('created_at',           sa.DateTime(),   nullable=True),
        sa.Column('expires_at',           sa.DateTime(),   nullable=False),
        sa.Column('used_at',              sa.DateTime(),   nullable=True),
        sa.Column('used_by_user_id',      sa.Integer(),    nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'],        ['user.id']),
        sa.ForeignKeyConstraint(['player_id'],            ['player.id']),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.ForeignKeyConstraint(['used_by_user_id'],      ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
    )
    op.create_index('ix_invite_token_token', 'invite_token', ['token'], unique=True)


def downgrade():
    op.drop_index('ix_invite_token_token', table_name='invite_token')
    op.drop_table('invite_token')
