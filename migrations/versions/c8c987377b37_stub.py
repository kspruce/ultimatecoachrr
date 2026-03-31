"""Stub for revision applied directly on server

Revision ID: c8c987377b37
Revises: c2d3e4f5a6b7
Create Date: 2026-03-31

This is a placeholder for a migration that was applied on the production
database but whose file was never committed to the repository.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c8c987377b37'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
