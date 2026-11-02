"""Leadership hub: shared ideas, articles and footage for leaders

Revision ID: b6d8f0a2c4e6
Revises: e8a1c3f5b7d9
Create Date: 2026-11-02 12:00:00.000000

Adds leadership_post, leadership_comment and leadership_read (all start
empty), and team_settings.discord_leaders_channel_id / _webhook_url for the
hub's optional private Discord channel. The hub uses the existing
leadership_handbook_enabled switch.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b6d8f0a2c4e6'
down_revision = 'e8a1c3f5b7d9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.add_column(sa.Column('discord_leaders_channel_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('discord_leaders_webhook_url', sa.String(length=255), nullable=True))

    op.create_table(
        'leadership_post',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), sa.ForeignKey('team_organization.id'), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('clip_id', sa.Integer(), sa.ForeignKey('clip.id', ondelete='SET NULL'), nullable=True),
        sa.Column('start_seconds', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('pinned', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('on_agenda', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_activity_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('leadership_post') as batch_op:
        batch_op.create_index('ix_leadership_post_team_organization_id', ['team_organization_id'])
        batch_op.create_index('ix_leadership_post_last_activity_at', ['last_activity_at'])

    op.create_table(
        'leadership_comment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('leadership_post.id', ondelete='CASCADE'), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('leadership_comment') as batch_op:
        batch_op.create_index('ix_leadership_comment_post_id', ['post_id'])

    op.create_table(
        'leadership_read',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('leadership_post.id', ondelete='CASCADE'), nullable=False),
        sa.Column('seen_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'post_id', name='uq_leadership_read_user_post'),
    )
    with op.batch_alter_table('leadership_read') as batch_op:
        batch_op.create_index('ix_leadership_read_user_id', ['user_id'])
        batch_op.create_index('ix_leadership_read_post_id', ['post_id'])


def downgrade():
    op.drop_table('leadership_read')
    op.drop_table('leadership_comment')
    op.drop_table('leadership_post')
    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.drop_column('discord_leaders_webhook_url')
        batch_op.drop_column('discord_leaders_channel_id')
