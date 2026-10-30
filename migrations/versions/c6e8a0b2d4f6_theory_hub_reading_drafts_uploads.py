"""Theory hub: drafts, uploaded photos, reading progress and assigned reading

Revision ID: c6e8a0b2d4f6
Revises: b5d7f9a1c3e6
Create Date: 2026-10-28 18:00:00.000000

- theory_topic.published (existing topics stay published) and updated_by
- section slugs and tag names are unique per team rather than across every
  team, so two teams can both have a "Defense" section or a "Zone" tag
- theory_image: photos uploaded from the editor, kept in the database
- theory_read: who has marked which topic as read
- theory_assignment: topics the coaches have asked the team to read
"""
from alembic import op
import sqlalchemy as sa


revision = 'c6e8a0b2d4f6'
down_revision = 'b5d7f9a1c3e6'
branch_labels = None
depends_on = None

# SQLite reflects unique constraints without names; this names them so the
# batch rebuild can drop them (Postgres reports the real name instead)
NAMING = {'uq': 'uq_%(table_name)s_%(column_0_name)s'}


def _swap_unique(table, column, new_name, new_columns):
    """Drop the single-column unique constraint on table.column and add
    new_name on new_columns."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    old = [c['name'] or f'uq_{table}_{column}' for c in inspector.get_unique_constraints(table)
           if c['column_names'] == [column]]
    # (Postgres also lists each unique constraint's own index here)
    old_indexes = [i['name'] for i in inspector.get_indexes(table)
                   if i.get('unique') and i['column_names'] == [column] and i['name'] not in old
                   and not i.get('duplicates_constraint')]
    with op.batch_alter_table(table, naming_convention=NAMING) as batch_op:
        for name in old:
            batch_op.drop_constraint(name, type_='unique')
        for name in old_indexes:
            batch_op.drop_index(name)
        batch_op.create_unique_constraint(new_name, new_columns)


def upgrade():
    with op.batch_alter_table('theory_topic') as batch_op:
        batch_op.add_column(sa.Column('published', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('updated_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_theory_topic_updated_by_user', 'user', ['updated_by'], ['id'])

    _swap_unique('theory_section', 'slug', 'uq_theory_section_team_slug', ['team_organization_id', 'slug'])
    _swap_unique('theory_tag', 'name', 'uq_theory_tag_team_name', ['team_organization_id', 'name'])

    op.create_table(
        'theory_image',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(length=50), nullable=False),
        sa.Column('data', sa.Text(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.ForeignKeyConstraint(['uploaded_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_theory_image_team_organization_id', 'theory_image', ['team_organization_id'])

    op.create_table(
        'theory_read',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['topic_id'], ['theory_topic.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'topic_id', name='uq_theory_read_user_topic'),
    )
    op.create_index('ix_theory_read_team_organization_id', 'theory_read', ['team_organization_id'])
    op.create_index('ix_theory_read_user_id', 'theory_read', ['user_id'])
    op.create_index('ix_theory_read_topic_id', 'theory_read', ['topic_id'])

    op.create_table(
        'theory_assignment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_organization_id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=False),
        sa.Column('assigned_by', sa.Integer(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_organization_id'], ['team_organization.id']),
        sa.ForeignKeyConstraint(['topic_id'], ['theory_topic.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('topic_id'),
    )
    op.create_index('ix_theory_assignment_team_organization_id', 'theory_assignment', ['team_organization_id'])


def downgrade():
    op.drop_index('ix_theory_assignment_team_organization_id', table_name='theory_assignment')
    op.drop_table('theory_assignment')
    for name in ('ix_theory_read_topic_id', 'ix_theory_read_user_id', 'ix_theory_read_team_organization_id'):
        op.drop_index(name, table_name='theory_read')
    op.drop_table('theory_read')
    op.drop_index('ix_theory_image_team_organization_id', table_name='theory_image')
    op.drop_table('theory_image')

    with op.batch_alter_table('theory_tag') as batch_op:
        batch_op.drop_constraint('uq_theory_tag_team_name', type_='unique')
        batch_op.create_unique_constraint('theory_tag_name_key', ['name'])
    with op.batch_alter_table('theory_section') as batch_op:
        batch_op.drop_constraint('uq_theory_section_team_slug', type_='unique')
        batch_op.create_unique_constraint('theory_section_slug_key', ['slug'])

    with op.batch_alter_table('theory_topic') as batch_op:
        batch_op.drop_constraint('fk_theory_topic_updated_by_user', type_='foreignkey')
        batch_op.drop_column('updated_by')
        batch_op.drop_column('published')
