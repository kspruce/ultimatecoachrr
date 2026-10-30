"""When a user was sent their getting-started reminder

Revision ID: e8a1c3f5b7d9
Revises: c4e6a8b0d2f5
Create Date: 2026-10-30 18:00:00.000000

- user_onboarding.nudged_at: the one email reminding a new user of the
  checklist steps they haven't done. Empty means not sent yet.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e8a1c3f5b7d9'
down_revision = 'c4e6a8b0d2f5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user_onboarding') as batch_op:
        batch_op.add_column(sa.Column('nudged_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('user_onboarding') as batch_op:
        batch_op.drop_column('nudged_at')
