"""Throws get their team: throw.team_organization_id from their point

Revision ID: e4f1b2c3d5a7
Revises: d3e0a1b2c4f6
Create Date: 2026-11-02 17:00:00.000000

The stat endpoints saved throws without a team, so deleting a team with
recorded games failed (its events were still referenced by the throws).
New throws are stamped by a listener (app/models/throws.py); this fills in
the ones already saved.
"""
from alembic import op


revision = 'e4f1b2c3d5a7'
down_revision = 'd3e0a1b2c4f6'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('UPDATE throw SET team_organization_id = '
               '(SELECT point.team_organization_id FROM point WHERE point.id = throw.point_id) '
               'WHERE team_organization_id IS NULL')


def downgrade():
    pass  # the team is right either way
