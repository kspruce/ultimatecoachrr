"""add is_superadmin to user

Revision ID: 441730e8e830
Revises: 7116f57dd6ec
Create Date: 2026-02-16

"""

from alembic import op
import sqlalchemy as sa

# ---- REQUIRED ALEMBIC IDENTIFIERS ----
revision = "441730e8e830"
down_revision = "7116f57dd6ec"
branch_labels = None
depends_on = None
# --------------------------------------


def upgrade():
    op.add_column(
        "user",
        sa.Column(
            "is_superadmin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Make username 'admin' global superadmin
    op.execute("UPDATE \"user\" SET is_superadmin = 1 WHERE username = 'admin'")


def downgrade():
    op.drop_column("user", "is_superadmin")
