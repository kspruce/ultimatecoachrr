"""
Quick Fix Script - Add share_token columns to session_plan table
Run this instead of using migrations if you're having trouble.

Usage:
    python add_share_token_columns.py
"""

import sqlite3
import sys
import os

def add_share_token_columns():
    """Add share_token and share_token_expires columns to session_plan table"""
    
    # Try to find the database file
    possible_paths = [
        'instance/ultimate_coach.db',
        'ultimate_coach.db',
        'instance/app.db',
        'app.db'
    ]
    
    db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            break
    
    if not db_path:
        print("ERROR: Could not find database file!")
        print("Searched in:")
        for path in possible_paths:
            print(f"  - {path}")
        print("\nPlease provide the path to your database:")
        db_path = input("> ").strip()
        
        if not os.path.exists(db_path):
            print(f"ERROR: Database file not found at: {db_path}")
            sys.exit(1)
    
    print(f"Using database: {db_path}")
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(session_plan)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'share_token' in columns:
            print("✓ share_token column already exists")
        else:
            print("Adding share_token column...")
            cursor.execute("ALTER TABLE session_plan ADD COLUMN share_token VARCHAR(64)")
            print("✓ share_token column added")
        
        if 'share_token_expires' in columns:
            print("✓ share_token_expires column already exists")
        else:
            print("Adding share_token_expires column...")
            cursor.execute("ALTER TABLE session_plan ADD COLUMN share_token_expires DATETIME")
            print("✓ share_token_expires column added")
        
        # Check if index exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='ix_session_plan_share_token'")
        if cursor.fetchone():
            print("✓ Index already exists")
        else:
            print("Creating index on share_token...")
            cursor.execute("CREATE UNIQUE INDEX ix_session_plan_share_token ON session_plan(share_token)")
            print("✓ Index created")
        
        # Commit changes
        conn.commit()
        conn.close()
        
        print("\n" + "="*50)
        print("SUCCESS! Database updated successfully.")
        print("="*50)
        print("\nNext steps:")
        print("1. Add the routes from session_guest_routes.py to your session.py")
        print("2. Create the detail_guest.html template")
        print("3. Add the share link UI to your detail.html")
        print("4. Restart your Flask application")
        print("\nTo mark migrations as up-to-date, run:")
        print("  flask db stamp head")
        
    except sqlite3.Error as e:
        print(f"\nERROR: Database error occurred: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    print("="*50)
    print("Share Token Column Addition Script")
    print("="*50)
    print()
    
    response = input("This will modify your database. Continue? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Aborted.")
        sys.exit(0)
    
    print()
    add_share_token_columns()
