"""One login on several teams: team memberships

Revision ID: d7e8f9a0b1c2
Revises: 52c437aed7f5
Create Date: 2026-10-23

- team_membership: a user's place on a team, with their role there. Every
  existing user becomes a member of their team with their current role
  (user.team_organization_id and user.role stay as their home team and
  their role on it).
- Users with no team but a linked player take the player's team as home.
- player.user_id is no longer unique on its own: a user has one player per
  team (unique user_id + team_organization_id).
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = 'd7e8f9a0b1c2'
down_revision = '52c437aed7f5'
branch_labels = None
depends_on = None


user = sa.table('user',
                sa.column('id', sa.Integer),
                sa.column('team_organization_id', sa.Integer),
                sa.column('role', sa.String),
                sa.column('created_at', sa.DateTime))
player = sa.table('player',
                  sa.column('user_id', sa.Integer),
                  sa.column('team_organization_id', sa.Integer))
membership = sa.table('team_membership',
                      sa.column('user_id', sa.Integer),
                      sa.column('team_organization_id', sa.Integer),
                      sa.column('role', sa.String),
                      sa.column('created_at', sa.DateTime))


def upgrade():
    op.create_table(
        'team_membership',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='player'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'team_organization_id', name='uq_team_membership_user_team'),
    )
    op.create_index('idx_team_membership_team', 'team_membership', ['team_organization_id'])

    # Team-less users with a linked player belong to the player's team
    player_team = (sa.select(player.c.team_organization_id)
                   .where(player.c.user_id == user.c.id, player.c.team_organization_id.isnot(None))
                   .limit(1).scalar_subquery())
    op.execute(user.update()
               .where(user.c.team_organization_id.is_(None))
               .where(sa.exists().where(player.c.user_id == user.c.id,
                                        player.c.team_organization_id.isnot(None)))
               .values(team_organization_id=player_team))

    op.execute(membership.insert().from_select(
        ['user_id', 'team_organization_id', 'role', 'created_at'],
        sa.select(user.c.id, user.c.team_organization_id,
                  sa.func.coalesce(user.c.role, 'player'),
                  sa.func.coalesce(user.c.created_at, datetime.utcnow()))
        .where(user.c.team_organization_id.isnot(None))))

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_id_only = [uc for uc in inspector.get_unique_constraints('player')
                    if uc['column_names'] == ['user_id']]
    if bind.dialect.name == 'sqlite':
        # Unnamed constraints get a name from the convention so they can go
        with op.batch_alter_table('player', naming_convention={
                'uq': 'uq_%(table_name)s_%(column_0_name)s'}) as batch_op:
            for uc in user_id_only:
                batch_op.drop_constraint(uc['name'] or 'uq_player_user_id', type_='unique')
            batch_op.create_unique_constraint('uq_player_user_team', ['user_id', 'team_organization_id'])
    else:
        for uc in user_id_only:
            op.drop_constraint(uc['name'], 'player', type_='unique')
        for index in inspector.get_indexes('player'):
            if index.get('unique') and index['column_names'] == ['user_id']:
                op.drop_index(index['name'], table_name='player')
        op.create_unique_constraint('uq_player_user_team', 'player', ['user_id', 'team_organization_id'])


def downgrade():
    with op.batch_alter_table('player') as batch_op:
        batch_op.drop_constraint('uq_player_user_team', type_='unique')
        batch_op.create_unique_constraint('player_user_id_key', ['user_id'])
    op.drop_index('idx_team_membership_team', table_name='team_membership')
    op.drop_table('team_membership')
