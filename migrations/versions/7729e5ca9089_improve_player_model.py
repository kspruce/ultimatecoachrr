"""Improve player model"""

from alembic import op
import sqlalchemy as sa

revision = "7729e5ca9089"
down_revision = "604817d23bd6"
branch_labels = None
depends_on = None


def upgrade():

    # ---- Attendance constraint ----
    with op.batch_alter_table("attendance") as batch_op:
        batch_op.create_unique_constraint(
            "unique_player_session",
            ["session_id", "player_id"]
        )

    # ---- Player improvements ----
    with op.batch_alter_table("player") as batch_op:

        # drop index referencing removed column
        batch_op.drop_index("idx_player_team")

        batch_op.add_column(sa.Column("joined_team_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("left_team_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

        batch_op.alter_column(
            "jersey_number",
            existing_type=sa.String(length=10),
            type_=sa.Integer(),
            existing_nullable=True
        )

        batch_op.drop_column("team")
        batch_op.drop_column("line_preference")

    # recreate index on new column
    op.create_index("idx_player_team", "player", ["team_organization_id"])

    # ---- User admin column ----
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_admin",
                sa.Boolean(),
                nullable=False,
                server_default="0"
            )
        )


def downgrade():

    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("is_admin")

    op.drop_index("idx_player_team", table_name="player")

    with op.batch_alter_table("player") as batch_op:

        batch_op.add_column(sa.Column("team", sa.String(length=50)))
        batch_op.add_column(sa.Column("line_preference", sa.String(length=20)))

        batch_op.alter_column(
            "jersey_number",
            existing_type=sa.Integer(),
            type_=sa.String(length=10),
            existing_nullable=True
        )

        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("left_team_date")
        batch_op.drop_column("joined_team_date")

        batch_op.create_index("idx_player_team", ["team"])

    with op.batch_alter_table("attendance") as batch_op:
        batch_op.drop_constraint("unique_player_session", type_="unique")