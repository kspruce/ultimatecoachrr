"""Team sign-up links, team join codes and site settings

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-16

- site_settings: one row of site-wide switches (open team registration).
- team_signup_invite: single-use links superadmins send to new clubs.
- team_organization.join_code / join_enabled: reusable link players use to
  join a team.
- invite_token.created_by_id becomes nullable so the coach who created an
  invite can be deleted.
- Placeholder emails (<username>@no-email.placeholder) become NULL: the
  column has allowed NULL for a while, and a fake address can't receive
  password-reset emails.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'site_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('open_team_registration', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'team_signup_invite',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('used_by_user_id', sa.Integer(), nullable=True),
        sa.Column('team_organization_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['used_by_user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_team_signup_invite_token', 'team_signup_invite', ['token'], unique=True)

    with op.batch_alter_table('team_organization', schema=None) as batch_op:
        batch_op.add_column(sa.Column('join_code', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('join_enabled', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.create_unique_constraint('uq_team_organization_join_code', ['join_code'])

    with op.batch_alter_table('invite_token', schema=None) as batch_op:
        batch_op.alter_column('created_by_id', existing_type=sa.Integer(), nullable=True)

    op.execute("UPDATE \"user\" SET email = NULL WHERE email LIKE '%@no-email.placeholder'")


def downgrade():
    with op.batch_alter_table('invite_token', schema=None) as batch_op:
        batch_op.alter_column('created_by_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('team_organization', schema=None) as batch_op:
        batch_op.drop_constraint('uq_team_organization_join_code', type_='unique')
        batch_op.drop_column('join_enabled')
        batch_op.drop_column('join_code')

    op.drop_index('ix_team_signup_invite_token', table_name='team_signup_invite')
    op.drop_table('team_signup_invite')
    op.drop_table('site_settings')
