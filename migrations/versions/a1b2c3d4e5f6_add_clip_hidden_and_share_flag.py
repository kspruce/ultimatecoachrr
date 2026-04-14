"""Add is_hidden and is_flagged_for_sharing to clip

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-04-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    # Wrap each in try/except so the migration is safe to re-run on SQLite
    # (which lacks IF NOT EXISTS for ALTER TABLE ADD COLUMN).
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
