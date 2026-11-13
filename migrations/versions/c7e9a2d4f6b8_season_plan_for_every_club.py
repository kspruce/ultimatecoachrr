"""Season plans for every club: per-squad week themes and a programme per phase

Revision ID: c7e9a2d4f6b8
Revises: f0b4d2e6a8c5
Create Date: 2026-11-13

The fixed 1s / 2s theme columns become a {squad name: theme} map, with the
plan's squads listed on the plan. Existing plans that used them get the
squads "1s" and "2s" and keep every theme.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c7e9a2d4f6b8'
down_revision = 'f0b4d2e6a8c5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('season_plan', schema=None) as batch_op:
        batch_op.add_column(sa.Column('squad_names', sa.JSON(), nullable=True))
    with op.batch_alter_table('season_week', schema=None) as batch_op:
        batch_op.add_column(sa.Column('squad_themes', sa.JSON(), nullable=True))
    with op.batch_alter_table('season_phase', schema=None) as batch_op:
        batch_op.add_column(sa.Column('programme_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_season_phase_programme', 'programme', ['programme_id'], ['id'],
                                    ondelete='SET NULL')

    conn = op.get_bind()
    week = sa.table('season_week', sa.column('id', sa.Integer), sa.column('plan_id', sa.Integer),
                    sa.column('firsts_theme', sa.Text), sa.column('seconds_theme', sa.Text),
                    sa.column('squad_themes', sa.JSON))
    plan = sa.table('season_plan', sa.column('id', sa.Integer), sa.column('squad_names', sa.JSON))
    plans_with_squads = set()
    for row in conn.execute(sa.select(week.c.id, week.c.plan_id, week.c.firsts_theme, week.c.seconds_theme)):
        themes = {k: v for k, v in (('1s', row.firsts_theme), ('2s', row.seconds_theme)) if v}
        if themes:
            conn.execute(week.update().where(week.c.id == row.id).values(squad_themes=themes))
            plans_with_squads.add(row.plan_id)
    for plan_id in plans_with_squads:
        conn.execute(plan.update().where(plan.c.id == plan_id).values(squad_names=['1s', '2s']))

    with op.batch_alter_table('season_week', schema=None) as batch_op:
        batch_op.drop_column('firsts_theme')
        batch_op.drop_column('seconds_theme')


def downgrade():
    with op.batch_alter_table('season_week', schema=None) as batch_op:
        batch_op.add_column(sa.Column('firsts_theme', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('seconds_theme', sa.Text(), nullable=True))

    conn = op.get_bind()
    week = sa.table('season_week', sa.column('id', sa.Integer), sa.column('firsts_theme', sa.Text),
                    sa.column('seconds_theme', sa.Text), sa.column('squad_themes', sa.JSON))
    for row in conn.execute(sa.select(week.c.id, week.c.squad_themes)):
        themes = row.squad_themes or {}
        if themes:
            conn.execute(week.update().where(week.c.id == row.id).values(
                firsts_theme=themes.get('1s'), seconds_theme=themes.get('2s')))

    with op.batch_alter_table('season_phase', schema=None) as batch_op:
        batch_op.drop_constraint('fk_season_phase_programme', type_='foreignkey')
        batch_op.drop_column('programme_id')
    with op.batch_alter_table('season_week', schema=None) as batch_op:
        batch_op.drop_column('squad_themes')
    with op.batch_alter_table('season_plan', schema=None) as batch_op:
        batch_op.drop_column('squad_names')
