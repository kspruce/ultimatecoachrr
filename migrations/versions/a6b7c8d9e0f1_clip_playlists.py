"""Clip playlists

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-10-22

- clip_playlist: an ordered set of clips to watch back to back.
- clip_playlist_item: one clip in a playlist, with its position and a note.
Both are only created if missing.
"""
from alembic import op
import sqlalchemy as sa


revision = 'a6b7c8d9e0f1'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade():
    existing = sa.inspect(op.get_bind()).get_table_names()
    if 'clip_playlist' not in existing:
        op.create_table(
            'clip_playlist',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('title', sa.String(length=120), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('team_organization_id', sa.Integer(), sa.ForeignKey('team_organization.id'),
                      nullable=False),
        )
    if 'clip_playlist_item' not in existing:
        op.create_table(
            'clip_playlist_item',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('playlist_id', sa.Integer(), sa.ForeignKey('clip_playlist.id'), nullable=False),
            sa.Column('clip_id', sa.Integer(), sa.ForeignKey('clip.id'), nullable=False),
            sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('note', sa.String(length=300), nullable=True),
            sa.Column('team_organization_id', sa.Integer(), sa.ForeignKey('team_organization.id'),
                      nullable=False),
        )


def downgrade():
    op.drop_table('clip_playlist_item')
    op.drop_table('clip_playlist')
