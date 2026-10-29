"""Plays can be drawn in the drill editor, and picked for a game plan

Revision ID: f0b2d4e6a8c1
Revises: e9a1c3d5f7b0
Create Date: 2026-10-24 15:00:00.000000

A drill diagram can now belong to a playbook play instead of a drill, so
plays are drawn, stored and served the same way. A scouting report lists
the plays we'll run against that team.
"""
from alembic import op
import sqlalchemy as sa


revision = 'f0b2d4e6a8c1'
down_revision = 'e9a1c3d5f7b0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('drill_diagram') as batch_op:
        batch_op.alter_column('saved_drill_id', existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column('play_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_drill_diagram_play', 'play', ['play_id'], ['id'], ondelete='CASCADE')
        batch_op.create_index('ix_drill_diagram_play_id', ['play_id'])

    op.create_table(
        'scouting_report_play',
        sa.Column('scouting_report_id', sa.Integer(),
                  sa.ForeignKey('scouting_report.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('play_id', sa.Integer(), sa.ForeignKey('play.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade():
    op.drop_table('scouting_report_play')
    op.execute('DELETE FROM drill_diagram WHERE play_id IS NOT NULL')
    with op.batch_alter_table('drill_diagram') as batch_op:
        batch_op.drop_index('ix_drill_diagram_play_id')
        batch_op.drop_constraint('fk_drill_diagram_play', type_='foreignkey')
        batch_op.drop_column('play_id')
        batch_op.alter_column('saved_drill_id', existing_type=sa.Integer(), nullable=False)
