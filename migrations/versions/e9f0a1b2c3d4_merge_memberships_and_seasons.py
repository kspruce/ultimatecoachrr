"""Merge the team memberships and seasons migrations

Revision ID: e9f0a1b2c3d4
Revises: d7e8f9a0b1c2, b4c5d6e7f8a9
Create Date: 2026-10-23

Both branched from the matchup roles migration and merged to main at the
same time; nothing to do but join them.
"""


revision = 'e9f0a1b2c3d4'
down_revision = ('d7e8f9a0b1c2', 'b4c5d6e7f8a9')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
