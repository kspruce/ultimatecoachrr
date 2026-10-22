"""Add the leadership handbook

Revision ID: f3b4c5d6e7f8
Revises: e4f5a6b7c8d9
Create Date: 2026-10-22 18:00:00.000000

Adds team_settings.leadership_handbook_enabled (false, so no team sees it
until it is switched on) and the handbook_page table, which starts empty.
"""
from alembic import op
import sqlalchemy as sa


revision = 'f3b4c5d6e7f8'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.add_column(sa.Column('leadership_handbook_enabled', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))

    op.create_table(
        'handbook_page',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('section', sa.String(length=40), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('lead', sa.Text(), nullable=True),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_organization_id', 'slug', name='uq_handbook_page_team_slug'),
    )
    with op.batch_alter_table('handbook_page') as batch_op:
        batch_op.create_index('ix_handbook_page_team_organization_id', ['team_organization_id'])


def downgrade():
    with op.batch_alter_table('handbook_page') as batch_op:
        batch_op.drop_index('ix_handbook_page_team_organization_id')
    op.drop_table('handbook_page')
    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.drop_column('leadership_handbook_enabled')
