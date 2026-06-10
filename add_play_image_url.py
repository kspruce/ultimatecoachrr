"""
Add image_url column to the play table (idempotent).

Safe to run on every deploy — it checks whether the column exists first.
Works with both Postgres (Railway) and SQLite (local) via the app's
SQLAlchemy engine.

Usage:
    python add_play_image_url.py
"""
from sqlalchemy import inspect, text

from app import create_app, db


def main():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [c['name'] for c in inspector.get_columns('play')]
        if 'image_url' in columns:
            print('play.image_url already exists - nothing to do')
            return
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE play ADD COLUMN image_url VARCHAR(255)'))
        print('Added image_url column to play table')


if __name__ == '__main__':
    main()
