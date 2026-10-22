"""Fitness hub: standard test keys and the leaderboard opt-in

Revision ID: e4f5a6b7c8d9
Revises: d1e2f3a4b5c6
Create Date: 2026-10-22

- fitness_metric.key: marks the shared metrics behind the four standard
  tests (created by the app on first use).
- player.fitness_leaderboard: players opt in to the fitness leaderboard;
  everyone starts opted out.
Both are only added if missing.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e4f5a6b7c8d9'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())

    columns = {c['name'] for c in inspector.get_columns('fitness_metric')}
    if 'key' not in columns:
        with op.batch_alter_table('fitness_metric', schema=None) as batch_op:
            batch_op.add_column(sa.Column('key', sa.String(length=40), nullable=True))
            batch_op.create_unique_constraint('uq_fitness_metric_key', ['key'])

    columns = {c['name'] for c in inspector.get_columns('player')}
    if 'fitness_leaderboard' not in columns:
        with op.batch_alter_table('player', schema=None) as batch_op:
            batch_op.add_column(sa.Column('fitness_leaderboard', sa.Boolean(), nullable=False,
                                          server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.drop_column('fitness_leaderboard')
    with op.batch_alter_table('fitness_metric', schema=None) as batch_op:
        batch_op.drop_constraint('uq_fitness_metric_key', type_='unique')
        batch_op.drop_column('key')
