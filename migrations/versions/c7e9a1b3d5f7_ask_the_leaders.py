"""Ask the leaders: players' questions in the Leadership hub

Revision ID: c7e9a1b3d5f7
Revises: b6d8f0a2c4e6
Create Date: 2026-11-02 15:00:00.000000

leadership_post gets from_player and what the post is about
(subject_type, subject_id); leadership_comment gets leaders_only, for notes
on a player's question that the player doesn't see.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c7e9a1b3d5f7'
down_revision = 'b6d8f0a2c4e6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('leadership_post') as batch_op:
        batch_op.add_column(sa.Column('from_player', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('subject_type', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('subject_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_leadership_post_author_id', ['author_id'])
    with op.batch_alter_table('leadership_comment') as batch_op:
        batch_op.add_column(sa.Column('leaders_only', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('leadership_comment') as batch_op:
        batch_op.drop_column('leaders_only')
    with op.batch_alter_table('leadership_post') as batch_op:
        batch_op.drop_index('ix_leadership_post_author_id')
        batch_op.drop_column('subject_id')
        batch_op.drop_column('subject_type')
        batch_op.drop_column('from_player')
