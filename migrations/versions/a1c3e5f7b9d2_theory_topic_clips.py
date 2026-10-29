"""Theory topics can link clips from the clip library

Revision ID: a1c3e5f7b9d2
Revises: f0b2d4e6a8c1
Create Date: 2026-10-28 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1c3e5f7b9d2'
down_revision = 'f0b2d4e6a8c1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'topic_clip_association',
        sa.Column('topic_id', sa.Integer(), sa.ForeignKey('theory_topic.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('clip_id', sa.Integer(), sa.ForeignKey('clip.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade():
    op.drop_table('topic_clip_association')
