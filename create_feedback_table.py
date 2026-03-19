"""
Emergency one-off: creates the player_feedback table directly via SQL,
then stamps alembic_version to the repo head so future migrations work.

Run on Applikku as a one-off command:
    python create_feedback_table.py
"""
from app import create_app, db
from sqlalchemy import text

app = create_app()

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS player_feedback (
    id          SERIAL PRIMARY KEY,
    player_id   INTEGER NOT NULL REFERENCES player(id),
    coach_id    INTEGER NOT NULL REFERENCES "user"(id),
    session_id  INTEGER REFERENCES session_plan(id),
    content     TEXT    NOT NULL,
    context_tag VARCHAR(50) NOT NULL DEFAULT 'General',
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_player_feedback_player_id  ON player_feedback(player_id);",
    "CREATE INDEX IF NOT EXISTS ix_player_feedback_coach_id   ON player_feedback(coach_id);",
    "CREATE INDEX IF NOT EXISTS ix_player_feedback_session_id ON player_feedback(session_id);",
]

TARGET_REVISION = 'c2d3e4f5a6b7'

with app.app_context():
    conn = db.engine.connect()
    trans = conn.begin()
    try:
        # 1. Create the table
        print("Creating player_feedback table...")
        conn.execute(text(CREATE_TABLE_SQL))
        for idx_sql in CREATE_INDEXES_SQL:
            conn.execute(text(idx_sql))
        print("  Table and indexes created.")

        # 2. Fix alembic_version
        print("Fixing alembic_version...")
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        print(f"  Current rows: {rows}")
        if rows:
            conn.execute(
                text("UPDATE alembic_version SET version_num = :rev"),
                {'rev': TARGET_REVISION}
            )
        else:
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
                {'rev': TARGET_REVISION}
            )
        rows_after = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        print(f"  Updated rows: {rows_after}")

        trans.commit()
        print("\nAll done. The player_feedback table is live.")
        print("Future migrations will run via 'flask db upgrade' as normal.")

    except Exception as e:
        trans.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        conn.close()
