"""Add user_onboarding for the getting-started guide

Revision ID: 77b543744ffe
Revises: d5e6f7a8b9c0
Create Date: 2026-10-16 12:00:00.000000

"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '77b543744ffe'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_onboarding',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('welcomed_role', sa.String(length=20), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(), nullable=True),
        sa.Column('completed_steps', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # People already using the app have found their way around: count them
    # as welcomed with the checklist hidden. "Getting started" in the user
    # menu still opens it.
    conn = op.get_bind()
    user = sa.table('user', sa.column('id', sa.Integer), sa.column('role', sa.String))
    onboarding = sa.table(
        'user_onboarding',
        sa.column('user_id', sa.Integer), sa.column('welcomed_role', sa.String),
        sa.column('dismissed_at', sa.DateTime), sa.column('completed_steps', sa.JSON),
        sa.column('updated_at', sa.DateTime),
    )
    now = datetime.utcnow()
    rows = [{'user_id': uid, 'welcomed_role': role, 'dismissed_at': now,
             'completed_steps': [], 'updated_at': now}
            for uid, role in conn.execute(sa.select(user.c.id, user.c.role))]
    if rows:
        op.bulk_insert(onboarding, rows)


def downgrade():
    op.drop_table('user_onboarding')
