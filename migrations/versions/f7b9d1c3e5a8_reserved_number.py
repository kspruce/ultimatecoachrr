"""Captains and coaches reserve or retire shirt numbers

Revision ID: f7b9d1c3e5a8
Revises: e5a7c9b1d3f6
Create Date: 2026-11-16

"""
from alembic import op
import sqlalchemy as sa


revision = 'f7b9d1c3e5a8'
down_revision = 'e5a7c9b1d3f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reserved_number',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_organization_id', 'number', name='uq_reserved_number_team'),
    )
    op.create_index('ix_reserved_number_team_organization_id', 'reserved_number', ['team_organization_id'])


def downgrade():
    op.drop_index('ix_reserved_number_team_organization_id', table_name='reserved_number')
    op.drop_table('reserved_number')
