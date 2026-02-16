"""Add feature toggles to team_settings

Revision ID: e3e44e60d100
Revises: 443f4ea75519
Create Date: 2026-02-16 10:45:47.313418

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3e44e60d100'
down_revision = '443f4ea75519'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.add_column(sa.Column('stats_enabled', sa.Boolean(), nullable=False, server_default='true'))
        batch_op.add_column(sa.Column('gameday_enabled', sa.Boolean(), nullable=False, server_default='true'))
        batch_op.add_column(sa.Column('playbook_enabled', sa.Boolean(), nullable=False, server_default='true'))
        batch_op.add_column(sa.Column('theory_enabled', sa.Boolean(), nullable=False, server_default='true'))
        batch_op.add_column(sa.Column('drills_enabled', sa.Boolean(), nullable=False, server_default='true'))
        batch_op.add_column(sa.Column('sessions_enabled', sa.Boolean(), nullable=False, server_default='true'))
        batch_op.add_column(sa.Column('clip_enabled', sa.Boolean(), nullable=False, server_default='true'))
        batch_op.add_column(sa.Column('scouting_enabled', sa.Boolean(), nullable=False, server_default='true'))
        batch_op.add_column(sa.Column('fitness_enabled', sa.Boolean(), nullable=False, server_default='true'))



def downgrade():
    with op.batch_alter_table('team_settings') as batch_op:
        batch_op.drop_column('fitness_enabled')
        batch_op.drop_column('scouting_enabled')
        batch_op.drop_column('clip_enabled')
        batch_op.drop_column('sessions_enabled')
        batch_op.drop_column('drills_enabled')
        batch_op.drop_column('theory_enabled')
        batch_op.drop_column('playbook_enabled')
        batch_op.drop_column('gameday_enabled')
        batch_op.drop_column('stats_enabled')

