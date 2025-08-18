# fix_database.py
import sqlite3
import os

# Path to your SQLite database file
db_path = 'app.db'  # Adjust this if your database is in a different location

# Check if the database file exists
if not os.path.exists(db_path):
    print(f"Database file {db_path} not found!")
    exit(1)

# Connect to the database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Create team_organization table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS team_organization (
        id INTEGER PRIMARY KEY,
        name VARCHAR(100) NOT NULL UNIQUE,
        slug VARCHAR(100) NOT NULL UNIQUE,
        description TEXT,
        logo VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Check if default team exists
    cursor.execute("SELECT id FROM team_organization WHERE slug = 'default-team'")
    result = cursor.fetchone()
    
    if not result:
        # Insert a default team
        cursor.execute('''
        INSERT INTO team_organization (name, slug, description, created_at) 
        VALUES ('Default Team', 'default-team', 'Default team created during migration', CURRENT_TIMESTAMP)
        ''')
    
    # Get the default team ID
    cursor.execute("SELECT id FROM team_organization WHERE slug = 'default-team'")
    default_team_id = cursor.fetchone()[0]
    
    # List of tables to add team_organization_id to
    tables = [
        'user', 'player', 'drill', 'tournament', 'game', 'session_plan',
        'fitness_metric', 'fitness_record'
    ]
    
    # Add team_organization_id to tables if it doesn't exist
    for table in tables:
        try:
            # Check if the table exists
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if cursor.fetchone():
                # Check if the column already exists
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [info[1] for info in cursor.fetchall()]
                
                if 'team_organization_id' not in columns:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN team_organization_id INTEGER REFERENCES team_organization(id)")
                    print(f"Added team_organization_id to {table}")
                    
                    # Update all records to use the default team
                    cursor.execute(f"UPDATE {table} SET team_organization_id = ? WHERE team_organization_id IS NULL", (default_team_id,))
                    print(f"Updated {cursor.rowcount} records in {table}")
        except Exception as e:
            print(f"Error processing table {table}: {e}")
    
    # Commit the changes
    conn.commit()
    print("Database updated successfully!")

except Exception as e:
    conn.rollback()
    print(f"Error updating database: {e}")

finally:
    conn.close()
