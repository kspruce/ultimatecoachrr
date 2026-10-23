"""Scouting: tags, game plan, key threats, matchups, clip moments

Revision ID: 52c437aed7f5
Revises: a6b7c8d9e0f1
Create Date: 2026-10-23 12:00:00.000000

Adds to scouting_report the offence/defence tags and the game plan
(overall, O-line, D-line); to opponent_player a key-threat flag and the
player of ours who marks them; to scouting_clip extra moments in the same
video and the opponent player the clip is about. Every new column is empty
(or false), so existing reports read exactly as before.
"""
from alembic import op
import sqlalchemy as sa


revision = '52c437aed7f5'
down_revision = 'a6b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('scouting_report') as batch_op:
        batch_op.add_column(sa.Column('offense_tags', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('defense_tags', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('game_plan', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('o_line_plan', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('d_line_plan', sa.Text(), nullable=True))

    with op.batch_alter_table('opponent_player') as batch_op:
        batch_op.add_column(sa.Column('is_key_threat', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column('matched_player_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_opponent_player_matched_player_id', 'player',
                                    ['matched_player_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('scouting_clip') as batch_op:
        batch_op.add_column(sa.Column('moments', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('opponent_player_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_scouting_clip_opponent_player_id', 'opponent_player',
                                    ['opponent_player_id'], ['id'], ondelete='SET NULL')


def _drop_foreign_key(table, column):
    """Drop the foreign key on table.column under whatever name it has: a
    database built by db.create_all() names them differently (or not at all)."""
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if fk['constrained_columns'] == [column] and fk.get('name'):
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_constraint(fk['name'], type_='foreignkey')


def downgrade():
    _drop_foreign_key('scouting_clip', 'opponent_player_id')
    with op.batch_alter_table('scouting_clip') as batch_op:
        batch_op.drop_column('opponent_player_id')
        batch_op.drop_column('moments')

    _drop_foreign_key('opponent_player', 'matched_player_id')
    with op.batch_alter_table('opponent_player') as batch_op:
        batch_op.drop_column('matched_player_id')
        batch_op.drop_column('is_key_threat')

    with op.batch_alter_table('scouting_report') as batch_op:
        batch_op.drop_column('d_line_plan')
        batch_op.drop_column('o_line_plan')
        batch_op.drop_column('game_plan')
        batch_op.drop_column('defense_tags')
        batch_op.drop_column('offense_tags')
