"""merge heads: improve_player_model + add_invite_token_table

Revision ID: b1c2d3e4f5a6
Revises: 7729e5ca9089, a9b8c7d6e5f4
Create Date: 2026-03-09

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = ('7729e5ca9089', 'a9b8c7d6e5f4')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
