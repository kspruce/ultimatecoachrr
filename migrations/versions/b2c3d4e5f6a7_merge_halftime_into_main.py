"""Merge halftime migration into main chain

Revision ID: b2c3d4e5f6a7
Revises: c8c987377b37, a1b2c3d4e5f6
Create Date: 2026-03-31

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = ('c8c987377b37', 'a1b2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
