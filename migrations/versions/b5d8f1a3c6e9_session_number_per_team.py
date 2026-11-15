"""Sessions get a per-team number for their URLs

Revision ID: b5d8f1a3c6e9
Revises: c7e9a2d4f6b8
Create Date: 2026-11-15

"""
from alembic import op
import sqlalchemy as sa


revision = 'b5d8f1a3c6e9'
down_revision = 'c7e9a2d4f6b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('session_plan', schema=None) as batch_op:
        batch_op.add_column(sa.Column('number', sa.Integer(), nullable=True))

    # Number each team's existing sessions 1, 2, 3... in the order they were made
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        'SELECT id, team_organization_id FROM session_plan '
        'ORDER BY team_organization_id, created_at, id')).fetchall()
    counts = {}
    updates = []
    for row in rows:
        counts[row.team_organization_id] = counts.get(row.team_organization_id, 0) + 1
        updates.append({'n': counts[row.team_organization_id], 'i': row.id})
    if updates:
        bind.execute(sa.text('UPDATE session_plan SET number = :n WHERE id = :i'), updates)

    with op.batch_alter_table('session_plan', schema=None) as batch_op:
        batch_op.alter_column('number', existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint('uq_session_plan_team_number',
                                          ['team_organization_id', 'number'])


def downgrade():
    with op.batch_alter_table('session_plan', schema=None) as batch_op:
        batch_op.drop_constraint('uq_session_plan_team_number', type_='unique')
        batch_op.drop_column('number')
