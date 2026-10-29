"""Team roles: the playbook's positions become roles players hold each season

Revision ID: c3e5a7b9d1f4
Revises: b2d4f6a8c0e3
Create Date: 2026-10-29 10:00:00.000000

- player_position (now a team role) gets a line (O / D / either), a short
  description and an order; existing ones keep their alphabetical order
- player_role: who holds which role in a season (assigned by coaches and
  captains, in depth order), and which roles players would like
"""
from alembic import op
import sqlalchemy as sa


revision = 'c3e5a7b9d1f4'
down_revision = 'b2d4f6a8c0e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('player_position') as batch_op:
        batch_op.add_column(sa.Column('line', sa.String(length=1), nullable=True))
        batch_op.add_column(sa.Column('description', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))

    bind = op.get_bind()
    position = sa.table('player_position', sa.column('id'), sa.column('name'),
                        sa.column('team_organization_id'), sa.column('sort_order'))
    rows = bind.execute(sa.select(position.c.id, position.c.team_organization_id)
                        .order_by(position.c.team_organization_id, position.c.name, position.c.id)).fetchall()
    numbers = {}
    for row_id, team_id in rows:
        numbers[team_id] = numbers.get(team_id, 0) + 1
        bind.execute(position.update().where(position.c.id == row_id).values(sort_order=numbers[team_id]))

    op.create_table(
        'player_role',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('season_roster_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('depth', sa.Integer(), nullable=False),
        sa.Column('is_main', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.ForeignKeyConstraint(['season_roster_id'], ['season_roster.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['player_position.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('season_roster_id', 'role_id', 'kind', name='uq_player_role_roster_role_kind'),
    )
    op.create_index('ix_player_role_team_organization_id', 'player_role', ['team_organization_id'])
    op.create_index('ix_player_role_season_roster_id', 'player_role', ['season_roster_id'])
    op.create_index('ix_player_role_role_id', 'player_role', ['role_id'])


def downgrade():
    op.drop_index('ix_player_role_role_id', table_name='player_role')
    op.drop_index('ix_player_role_season_roster_id', table_name='player_role')
    op.drop_index('ix_player_role_team_organization_id', table_name='player_role')
    op.drop_table('player_role')
    with op.batch_alter_table('player_position') as batch_op:
        batch_op.drop_column('sort_order')
        batch_op.drop_column('description')
        batch_op.drop_column('line')
