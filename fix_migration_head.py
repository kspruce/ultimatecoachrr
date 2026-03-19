"""
One-off script: forcibly sets the alembic_version table to the repo's
current head revision (c2d3e4f5a6b7), bypassing Alembic's chain validation.

Run once on production via:
    python fix_migration_head.py

Then immediately follow with:
    flask db upgrade
"""
from app import create_app, db
from sqlalchemy import text

TARGET_REVISION = 'c2d3e4f5a6b7'

app = create_app()

with app.app_context():
    # Check what's currently in the table
    current = db.session.execute(
        text("SELECT version_num FROM alembic_version")
    ).fetchall()
    print(f"Current alembic_version rows: {current}")

    if current:
        db.session.execute(
            text("UPDATE alembic_version SET version_num = :rev"),
            {'rev': TARGET_REVISION}
        )
    else:
        db.session.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
            {'rev': TARGET_REVISION}
        )

    db.session.commit()

    # Confirm
    result = db.session.execute(
        text("SELECT version_num FROM alembic_version")
    ).fetchall()
    print(f"Updated alembic_version rows: {result}")
    print("Done. Now run: flask db upgrade")
