"""Allow empty point_outcome, bring play.image_url/sort_order under Alembic,
and reset Postgres id sequences

Revision ID: a7b8c9d0e1f2
Revises: f7a8b9c0d1e2
Create Date: 2026-10-15

- point.point_outcome: undoing a goal sets it back to empty while the point
  is still in progress, which the NOT NULL constraint refused.
- play.image_url and play.sort_order were added by add_play_image_url.py and
  by create_app() on every boot; they're only added here if missing, so this
  is safe on the live database where they already exist.
- Every table's id sequence is moved past its highest id, so the app can let
  Postgres assign ids instead of computing max(id) + 1 (Postgres only).
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7b8c9d0e1f2'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    with op.batch_alter_table('point', schema=None) as batch_op:
        batch_op.alter_column('point_outcome', existing_type=sa.String(length=20), nullable=True)

    play_columns = {c['name'] for c in inspector.get_columns('play')}
    with op.batch_alter_table('play', schema=None) as batch_op:
        if 'image_url' not in play_columns:
            batch_op.add_column(sa.Column('image_url', sa.String(length=255), nullable=True))
        if 'sort_order' not in play_columns:
            batch_op.add_column(sa.Column('sort_order', sa.Integer(), nullable=True))

    if bind.dialect.name == 'postgresql':
        for table in inspector.get_table_names():
            if 'id' not in {c['name'] for c in inspector.get_columns(table)}:
                continue
            seq = bind.execute(sa.text('SELECT pg_get_serial_sequence(:t, :c)'),
                               {'t': f'"{table}"', 'c': 'id'}).scalar()
            if seq:
                bind.execute(sa.text(
                    f'SELECT setval(:seq, COALESCE((SELECT MAX(id) FROM "{table}"), 0) + 1, false)'),
                    {'seq': seq})


def downgrade():
    # The play columns and sequence positions are left as they are.
    op.execute("UPDATE point SET point_outcome = '' WHERE point_outcome IS NULL")
    with op.batch_alter_table('point', schema=None) as batch_op:
        batch_op.alter_column('point_outcome', existing_type=sa.String(length=20), nullable=False)
