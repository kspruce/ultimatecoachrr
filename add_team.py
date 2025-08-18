# add_team_org_columns.py
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    # Create team_organization table if it doesn't exist
    db.session.execute(text("""
    CREATE TABLE IF NOT EXISTS team_organization (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL UNIQUE,
        slug VARCHAR(100) NOT NULL UNIQUE,
        description TEXT,
        logo VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """))
    
    # Check if default team exists
    result = db.session.execute(text("SELECT id FROM team_organization WHERE slug = 'default-team'")).fetchone()
    
    if not result:
        # Insert a default team
        db.session.execute(text("""
        INSERT INTO team_organization (name, slug, description, created_at) 
        VALUES ('Default Team', 'default-team', 'Default team created during migration', CURRENT_TIMESTAMP)
        """))
        db.session.commit()
    
    # Get the default team ID
    default_team_id = db.session.execute(text("SELECT id FROM team_organization WHERE slug = 'default-team'")).fetchone()[0]
    
    # List of tables to add team_organization_id to
    tables = [
        'fitness_metric', 'fitness_record', 'user', 'player', 'drill', 'tournament', 
        'game', 'session_plan', 'clip', 'clip_tag', 'line_template', 'line_template_player', 
        'gameday_event', 'gameday_player_stats', 'attendance', 'session_rsvp', 
        'session_component', 'saved_drill', 'scouting_report', 'opponent_player', 
        'scouting_clip', 'player_point_stats', 'export_log'
    ]
    
    # Add team_organization_id to tables if it doesn't exist
    for table in tables:
        try:
            # Check if the column already exists
            result = db.session.execute(text(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table}' AND column_name = 'team_organization_id'
            """)).fetchone()
            
            if not result:
                print(f"Adding team_organization_id to {table}...")
                db.session.execute(text(f"""
                ALTER TABLE {table} ADD COLUMN team_organization_id INTEGER REFERENCES team_organization(id)
                """))
                
                # Update all records to use the default team
                db.session.execute(text(f"""
                UPDATE {table} SET team_organization_id = {default_team_id} WHERE team_organization_id IS NULL
                """))
                print(f"Updated {table} with default team ID")
        except Exception as e:
            print(f"Error processing table {table}: {e}")
    
    # Commit all changes
    db.session.commit()
    print("Database updated successfully!")
