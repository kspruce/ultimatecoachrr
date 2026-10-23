"""Clip share links can be revoked

Revision ID: f5a6b7c8d9e0
Revises: f3b4c5d6e7f8
Create Date: 2026-10-22

- clip.share_version: goes into every share link; bumping it revokes the
  links already handed out. Only added if missing.
"""
from alembic import op
import sqlalchemy as sa


revision = 'f5a6b7c8d9e0'
down_revision = 'f3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing_cols = [c['name'] for c in inspector.get_columns('clip')]
    if 'share_version' not in existing_cols:
        op.add_column('clip', sa.Column('share_version', sa.Integer(), nullable=False,
                                        server_default='0'))


def downgrade():
    op.drop_column('clip', 'share_version')
