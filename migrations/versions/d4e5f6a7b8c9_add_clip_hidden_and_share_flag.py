"""Add is_hidden and is_flagged_for_sharing to clip

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-04-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [c['name'] for c in inspector.get_columns('clip')]

    if 'is_hidden' not in existing_cols:
        op.add_column('clip', sa.Column('is_hidden', sa.Boolean(), nullable=False,
                                        server_default=sa.false()))

    if 'is_flagged_for_sharing' not in existing_cols:
        op.add_column('clip', sa.Column('is_flagged_for_sharing', sa.Boolean(), nullable=False,
                                        server_default=sa.false()))


def downgrade():
    op.drop_column('clip', 'is_flagged_for_sharing')
    op.drop_column('clip', 'is_hidden')
