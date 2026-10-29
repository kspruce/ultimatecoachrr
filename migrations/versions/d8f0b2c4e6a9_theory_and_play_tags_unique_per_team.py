"""Play tag names are unique per team

Revision ID: d8f0b2c4e6a9
Revises: c6e8a0b2d4f7
Create Date: 2026-10-24 12:30:00.000000

They were unique across the whole site, so a second team couldn't add an
"Endzone" tag once another team had one. (Theory section slugs and tag
names got the same change in c6e8a0b2d4f6.)
"""
from alembic import op
import sqlalchemy as sa


revision = 'd8f0b2c4e6a9'
down_revision = 'c6e8a0b2d4f7'
branch_labels = None
depends_on = None


# (table, column, new constraint)
CHANGES = [
    ('play_tag', 'name', 'uq_play_tag_team_name'),
]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, column, name in CHANGES:
        site_wide = [uc for uc in inspector.get_unique_constraints(table)
                     if uc['column_names'] == [column]]
        if bind.dialect.name == 'sqlite':
            # Unnamed constraints get a name from the convention so they can go
            with op.batch_alter_table(table, naming_convention={
                    'uq': 'uq_%(table_name)s_%(column_0_name)s'}) as batch_op:
                for uc in site_wide:
                    batch_op.drop_constraint(uc['name'] or f'uq_{table}_{column}', type_='unique')
                batch_op.create_unique_constraint(name, ['team_organization_id', column])
        else:
            for uc in site_wide:
                op.drop_constraint(uc['name'], table, type_='unique')
            for index in inspector.get_indexes(table):
                if index.get('unique') and index['column_names'] == [column]:
                    op.drop_index(index['name'], table_name=table)
            op.create_unique_constraint(name, table, ['team_organization_id', column])


def downgrade():
    for table, column, name in CHANGES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(name, type_='unique')
            batch_op.create_unique_constraint(f'{table}_{column}_key', [column])
