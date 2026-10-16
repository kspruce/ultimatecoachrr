"""Add fitness_goal and drill_diagram.editor_json

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-16

- fitness_goal: a player's target on a fitness metric (the goal pages were
  built before the table existed).
- drill_diagram.editor_json: the editable drawing behind a diagram made in
  the drill editor.
Both are only added if missing.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())

    if 'fitness_goal' not in inspector.get_table_names():
        op.create_table(
            'fitness_goal',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('player_id', sa.Integer(),
                      sa.ForeignKey('player.id', ondelete='CASCADE'), nullable=False),
            sa.Column('metric_id', sa.Integer(),
                      sa.ForeignKey('fitness_metric.id', ondelete='CASCADE'), nullable=False),
            sa.Column('target_value', sa.Float(), nullable=False),
            sa.Column('target_date', sa.Date(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('completed', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('completed_date', sa.DateTime(), nullable=True),
            sa.Column('created_by', sa.Integer(),
                      sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('team_organization_id', sa.Integer(),
                      sa.ForeignKey('team_organization.id'), nullable=True),
        )
        op.create_index('ix_fitness_goal_player_id', 'fitness_goal', ['player_id'])
        op.create_index('ix_fitness_goal_team_organization_id', 'fitness_goal',
                        ['team_organization_id'])

    columns = {c['name'] for c in inspector.get_columns('drill_diagram')}
    if 'editor_json' not in columns:
        with op.batch_alter_table('drill_diagram', schema=None) as batch_op:
            batch_op.add_column(sa.Column('editor_json', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('drill_diagram', schema=None) as batch_op:
        batch_op.drop_column('editor_json')
    op.drop_index('ix_fitness_goal_team_organization_id', table_name='fitness_goal')
    op.drop_index('ix_fitness_goal_player_id', table_name='fitness_goal')
    op.drop_table('fitness_goal')
