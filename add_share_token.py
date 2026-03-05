#!/usr/bin/env python3
"""
Add share_token columns to session_plan table
Run this script inside your web container
"""

from app import app, db
from sqlalchemy import text

def add_share_token_columns():
    """Add share_token and share_token_expires columns to session_plan table"""
    
    with app.app_context():
        try:
            print("Adding share_token column...")
            db.session.execute(text(
                "ALTER TABLE session_plan ADD COLUMN IF NOT EXISTS share_token VARCHAR(64)"
            ))
            print("✓ share_token column added")
            
            print("Adding share_token_expires column...")
            db.session.execute(text(
                "ALTER TABLE session_plan ADD COLUMN IF NOT EXISTS share_token_expires TIMESTAMP"
            ))
            print("✓ share_token_expires column added")
            
            print("Creating index on share_token...")
            db.session.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_session_plan_share_token ON session_plan(share_token)"
            ))
            print("✓ Index created")
            
            db.session.commit()
            print("\n✓ SUCCESS! All columns added successfully.")
            print("Restart your web container: docker compose restart web")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n✗ ERROR: {e}")
            return False
    
    return True

if __name__ == '__main__':
    add_share_token_columns()
