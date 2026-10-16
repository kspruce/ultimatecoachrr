"""Add team colours to team_settings

Revision ID: d5e6f7a8b9c0
Revises: c9d0e1f2a3b4
Create Date: 2026-10-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.add_column(sa.Column('primary_color', sa.String(length=7), nullable=True))
        batch_op.add_column(sa.Column('accent_color', sa.String(length=7), nullable=True))
        batch_op.add_column(sa.Column('show_kit_stripe', sa.Boolean(), nullable=False, server_default='true'))


def downgrade():
    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.drop_column('show_kit_stripe')
        batch_op.drop_column('accent_color')
        batch_op.drop_column('primary_color')
