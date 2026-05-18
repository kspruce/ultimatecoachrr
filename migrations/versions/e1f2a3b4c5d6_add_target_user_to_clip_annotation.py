"""Add target_user_id to clip_annotation for player-specific private notes

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-05-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('clip_annotation', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('target_user_id', sa.Integer(),
                      sa.ForeignKey('user.id'),
                      nullable=True)
        )


def downgrade():
    with op.batch_alter_table('clip_annotation', schema=None) as batch_op:
        batch_op.drop_column('target_user_id')
