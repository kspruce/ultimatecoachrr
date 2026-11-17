"""Shirt numbers are whole numbers in the database

Revision ID: b8d0f2a4c6e8
Revises: a1c3e5b7d9f2
Create Date: 2026-11-17

Migration 7729e5ca9089 changed player.jersey_number from text to a whole
number, but a database where that didn't take still holds text. Numbers
then come back as "12" rather than 12, so the Numbers page thinks every
number is free. This converts the column (and season_roster's, to be
safe) wherever it is still text: values that are whole numbers are kept,
anything else (e.g. "A1") is cleared and counted in the log.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b8d0f2a4c6e8'
down_revision = 'a1c3e5b7d9f2'
branch_labels = None
depends_on = None

TABLES = ('player', 'season_roster')


def jersey_number_to_integer(bind):
    """Convert jersey_number to INTEGER where it's still text (Postgres only;
    SQLite doesn't enforce column types). Returns {table: values cleared}."""
    cleared = {}
    if bind.dialect.name != 'postgresql':
        return cleared
    inspector = sa.inspect(bind)
    for table in TABLES:
        if table not in inspector.get_table_names():
            continue
        column = next((c for c in inspector.get_columns(table) if c['name'] == 'jersey_number'), None)
        if column is None or isinstance(column['type'], sa.Integer):
            continue
        cleared[table] = bind.execute(sa.text(
            f"SELECT count(*) FROM {table} WHERE jersey_number IS NOT NULL "
            f"AND btrim(jersey_number) !~ '^[0-9]+$'")).scalar()
        bind.execute(sa.text(
            f"ALTER TABLE {table} ALTER COLUMN jersey_number TYPE INTEGER USING "
            f"CASE WHEN btrim(jersey_number) ~ '^[0-9]+$' THEN btrim(jersey_number)::integer END"))
    return cleared


def upgrade():
    cleared = jersey_number_to_integer(op.get_bind())
    for table, count in cleared.items():
        print(f'{table}.jersey_number is now a whole number ({count} value(s) that weren\'t numbers cleared)')


def downgrade():
    pass  # the column was always meant to be a whole number
