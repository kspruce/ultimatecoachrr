"""Player development: goals as items (notes can be about one) and reviews

Revision ID: b3d5f7a9c1e3
Revises: a2c4e6f8b0d2
Create Date: 2026-10-31 18:00:00.000000

- player_goal: a player's goals, one per row, with a horizon (1-3 months,
  3-6 months, 6+ months, skill to develop) and a status. Each line of the old
  goal boxes on the player (short/mid/long-term goals, skills to develop)
  becomes a goal; the old columns are left as they were.
- player_feedback.goal_id: the goal a note is about
- player_review: written reviews (what's gone well, what to work on, next
  steps), coaches only until shared, with the player's comment
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = 'b3d5f7a9c1e3'
down_revision = 'a2c4e6f8b0d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'player_goal',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_organization_id', sa.Integer(), sa.ForeignKey('team_organization.id'), nullable=False),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('player.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('horizon', sa.String(length=10), nullable=False, server_default='short'),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='active'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('done_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_player_goal_team_organization_id', 'player_goal', ['team_organization_id'])
    op.create_index('ix_player_goal_player_id', 'player_goal', ['player_id'])

    with op.batch_alter_table('player_feedback') as batch_op:
        batch_op.add_column(sa.Column('goal_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_player_feedback_goal', 'player_goal', ['goal_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_player_feedback_goal_id', ['goal_id'])

    op.create_table(
        'player_review',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_organization_id', sa.Integer(), sa.ForeignKey('team_organization.id'), nullable=False),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('player.id', ondelete='CASCADE'), nullable=False),
        sa.Column('coach_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('went_well', sa.Text(), nullable=True),
        sa.Column('work_on', sa.Text(), nullable=True),
        sa.Column('next_steps', sa.Text(), nullable=True),
        sa.Column('player_comment', sa.Text(), nullable=True),
        sa.Column('shared', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('seen_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_player_review_team_organization_id', 'player_review', ['team_organization_id'])
    op.create_index('ix_player_review_player_id', 'player_review', ['player_id'])

    # The old goal boxes: one goal per line
    bind = op.get_bind()
    meta = sa.MetaData()
    player = sa.Table('player', meta, autoload_with=bind)
    goal = sa.Table('player_goal', meta, autoload_with=bind)
    columns = [('short_term_goals', 'short'), ('mid_term_goals', 'mid'), ('long_term_goals', 'long'),
               ('skills_to_develop', 'skill')]
    have = [(c, h) for c, h in columns if c in player.c]
    if not have:
        return
    now = datetime.utcnow()
    rows = bind.execute(sa.select(player.c.id, player.c.team_organization_id, *[player.c[c] for c, _ in have])
                        .where(player.c.team_organization_id.isnot(None))).all()
    for row in rows:
        for column, horizon in have:
            for line in (getattr(row, column) or '').splitlines():
                line = line.strip(' -•*\t')
                if line:
                    bind.execute(goal.insert().values(team_organization_id=row.team_organization_id, player_id=row.id,
                                                      title=line[:200], horizon=horizon, status='active',
                                                      created_at=now, updated_at=now))


def downgrade():
    op.drop_index('ix_player_review_player_id', table_name='player_review')
    op.drop_index('ix_player_review_team_organization_id', table_name='player_review')
    op.drop_table('player_review')
    with op.batch_alter_table('player_feedback') as batch_op:
        batch_op.drop_index('ix_player_feedback_goal_id')
        batch_op.drop_constraint('fk_player_feedback_goal', type_='foreignkey')
        batch_op.drop_column('goal_id')
    op.drop_index('ix_player_goal_player_id', table_name='player_goal')
    op.drop_index('ix_player_goal_team_organization_id', table_name='player_goal')
    op.drop_table('player_goal')
