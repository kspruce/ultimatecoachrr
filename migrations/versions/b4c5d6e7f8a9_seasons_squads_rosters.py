"""Seasons, squads and season rosters

Revision ID: b4c5d6e7f8a9
Revises: 52c437aed7f5
Create Date: 2026-10-23 15:00:00.000000

Adds the season, squad and season_roster tables, and season_id (plus
squad_id on games and tournaments) to game, tournament and session_plan.
The new tables start empty and every new column is empty, so nothing
changes until a team is first opened (or `flask backfill-seasons` runs):
that makes a season for each year the team has data in, puts each game,
tournament and session in its season and fills the rosters from who played.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b4c5d6e7f8a9'
down_revision = '52c437aed7f5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'squad',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_organization_id', 'name', name='uq_squad_team_name'),
    )
    op.create_index('ix_squad_team_organization_id', 'squad', ['team_organization_id'])

    op.create_table(
        'season',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_organization_id', 'year', name='uq_season_team_year'),
    )
    op.create_index('ix_season_team_organization_id', 'season', ['team_organization_id'])
    op.create_index('uq_season_one_current', 'season', ['team_organization_id'], unique=True,
                    sqlite_where=sa.text('is_current = 1'), postgresql_where=sa.text('is_current'))

    op.create_table(
        'season_roster',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('season_id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('squad_id', sa.Integer(), nullable=True),
        sa.Column('jersey_number', sa.Integer(), nullable=True),
        sa.Column('position', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('joined_date', sa.Date(), nullable=True),
        sa.Column('left_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.ForeignKeyConstraint(['season_id'], ['season.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['squad_id'], ['squad.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('season_id', 'player_id', name='uq_season_roster_player'),
    )
    op.create_index('ix_season_roster_team_organization_id', 'season_roster', ['team_organization_id'])
    op.create_index('ix_season_roster_season_id', 'season_roster', ['season_id'])
    op.create_index('ix_season_roster_player_id', 'season_roster', ['player_id'])

    for table, squad in (('game', True), ('tournament', True), ('session_plan', False)):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column('season_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(f'fk_{table}_season_id', 'season', ['season_id'], ['id'],
                                        ondelete='SET NULL')
            batch_op.create_index(f'ix_{table}_season_id', ['season_id'])
            if squad:
                batch_op.add_column(sa.Column('squad_id', sa.Integer(), nullable=True))
                batch_op.create_foreign_key(f'fk_{table}_squad_id', 'squad', ['squad_id'], ['id'],
                                            ondelete='SET NULL')


def downgrade():
    for table, squad in (('session_plan', False), ('tournament', True), ('game', True)):
        with op.batch_alter_table(table) as batch_op:
            if squad:
                batch_op.drop_constraint(f'fk_{table}_squad_id', type_='foreignkey')
                batch_op.drop_column('squad_id')
            batch_op.drop_index(f'ix_{table}_season_id')
            batch_op.drop_constraint(f'fk_{table}_season_id', type_='foreignkey')
            batch_op.drop_column('season_id')
    op.drop_table('season_roster')
    op.drop_index('uq_season_one_current', table_name='season')
    op.drop_table('season')
    op.drop_table('squad')
