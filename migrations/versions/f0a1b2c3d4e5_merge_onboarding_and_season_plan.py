"""Merge the onboarding and season plan migrations

Revision ID: f0a1b2c3d4e5
Revises: 77b543744ffe, e8f9a0b1c2d3
Create Date: 2026-10-16 15:00:00.000000

Both branched from d5e6f7a8b9c0; this joins them so there is one head.
"""

revision = 'f0a1b2c3d4e5'
down_revision = ('77b543744ffe', 'e8f9a0b1c2d3')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
