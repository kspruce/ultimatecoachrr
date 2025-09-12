from app import create_app, db
# Import models directly from app.models
from app.models.user import User
from app.models.player import Player
from app.models.tournament import Tournament
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.event import Event, Pull
from app.models.clip import Clip, ClipTag
from app.models.session import SessionPlan, SessionComponent, Attendance
from app.models.cutting_skill import CuttingSkill
from app.models.theory import TheorySection
from app.models.fitness import FitnessMetric, FitnessRecord
from app.models.gameday import LineTemplate, LineTemplatePlayer, GameDayEvent, GameDayPlayerStats
from app.models.team_organization import TeamOrganization  # Add this import
from app.models.drill import SavedDrill  # Make sure this is imported correctly
from datetime import datetime
import sys
from sqlalchemy import text, inspect
import os
import argparse

# Disable Discord integration by setting environment variable
os.environ['DISCORD_ENABLED'] = 'False'

# Create app with Discord disabled
app = create_app()

def print_status(message):
    """Helper function to print status messages"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def reset_database():
    """Reset and initialize the database"""
    with app.app_context():
        try:
            print_status("Starting database reset with Discord integration disabled...")
            
            # Execute DROP CASCADE for all tables
            db.session.execute(text("DROP SCHEMA public CASCADE"))
            db.session.execute(text("CREATE SCHEMA public"))
            db.session.commit()
            print_status("Dropped all tables with CASCADE")
            
            # Create all tables
            db.create_all()
            print_status("Created all tables")
            
            # Create default team organization
            default_team = TeamOrganization(
                name='Default Team',
                slug='default-team',
                description='Default team created during database reset'
            )
            db.session.add(default_team)
            db.session.commit()
            print_status("Created default team organization")
            
            # Create admin user
            admin = User(
                username='admin', 
                email='admin@example.com', 
                role='admin',
                team_organization_id=default_team.id  # Assign to default team
            )
            admin.set_password('password')
            db.session.add(admin)
            
            # Create bonus user
            bonus = User(
                username='bonus', 
                email='bonus@example.com', 
                role='player',
                team_organization_id=default_team.id  # Assign to default team
            )
            bonus.set_password('bonusboys')
            db.session.add(bonus)
            
            # Create captain users with coach role
            etaylor = User(
                username='etaylor', 
                email='et@example.com', 
                role='coach',
                team_organization_id=default_team.id  # Assign to default team
            )
            etaylor.set_password('Taylor35')
            db.session.add(etaylor)
            
            cspearing = User(
                username='cspearing', 
                email='cs@example.com', 
                role='coach',
                team_organization_id=default_team.id  # Assign to default team
            )
            cspearing.set_password('Spearing1')
            db.session.add(cspearing)
            
            bleung = User(
                username='bleung', 
                email='bl@example.com', 
                role='coach',
                team_organization_id=default_team.id  # Assign to default team
            )
            bleung.set_password('Leung18')
            db.session.add(bleung)
            
            # Create a stat taker user
            stat_taker = User(
                username='stats', 
                email='stats@example.com', 
                role='stat_taker',
                team_organization_id=default_team.id  # Assign to default team
            )
            stat_taker.set_password('stats123')
            db.session.add(stat_taker)
            
            db.session.commit()
            print_status("Created admin, captains, stat taker and bonus users")

            # Rest of your reset_database function...
            # [Your existing code for adding players, tournaments, etc.]

        except Exception as e:
            print_status(f"Error: {str(e)}")
            db.session.rollback()
            sys.exit(1)

def check_column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns

def migrate_user_roles():
    """Migrate existing users to the new role system"""
    with app.app_context():
        try:
            print_status("Starting user role migration...")
            
            # First check if is_admin column exists
            has_is_admin = check_column_exists('user', 'is_admin')
            
            if has_is_admin:
                print_status("Found is_admin column, migrating based on that...")
                # Update admin users
                db.session.execute(
                    text("UPDATE \"user\" SET role = 'admin' WHERE is_admin = TRUE AND (role = 'user' OR role IS NULL)")
                )
                
                # Update regular users
                db.session.execute(
                    text("UPDATE \"user\" SET role = 'player' WHERE is_admin = FALSE AND (role = 'user' OR role IS NULL)")
                )
            else:
                print_status("No is_admin column found, checking if we need to add default roles...")
                # Just set default roles for users without a role
                db.session.execute(
                    text("UPDATE \"user\" SET role = 'player' WHERE role = 'user' OR role IS NULL")
                )
            
            # Add the is_admin column if it doesn't exist
            if not has_is_admin:
                print_status("Adding is_admin column to user table...")
                db.session.execute(
                    text("ALTER TABLE \"user\" ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
                )
                # Set is_admin=True for admin users
                db.session.execute(
                    text("UPDATE \"user\" SET is_admin = TRUE WHERE role = 'admin'")
                )
            
            db.session.commit()
            print_status("User role migration completed successfully!")
            
        except Exception as e:
            print_status(f"Error during migration: {str(e)}")
            db.session.rollback()
            sys.exit(1)

def add_stat_taker_role():
    """Add a stat_taker role to the database if it doesn't exist"""
    with app.app_context():
        try:
            print_status("Checking for stat_taker users...")
            
            # Check if we have any stat_taker users
            result = db.session.execute(
                text("SELECT COUNT(*) FROM \"user\" WHERE role = 'stat_taker'")
            ).scalar()
            
            if result == 0:
                print_status("No stat_taker users found, creating one...")
                # Create a stat taker user
                stat_taker = User(username='stats', email='stats@example.com', role='stat_taker')
                stat_taker.set_password('stats123')
                db.session.add(stat_taker)
                db.session.commit()
                print_status("Created stat_taker user")
            else:
                print_status(f"Found {result} stat_taker users, no need to create more")
            
        except Exception as e:
            print_status(f"Error adding stat_taker role: {str(e)}")
            db.session.rollback()
            sys.exit(1)

def add_team_organization():
    """Add team_organization table and columns to existing tables"""
    with app.app_context():
        try:
            print_status("Starting team organization setup...")
            
            # Check if team_organization table exists
            inspector = inspect(db.engine)
            has_team_org_table = 'team_organization' in inspector.get_table_names()
            
            if not has_team_org_table:
                print_status("Creating team_organization table...")
                # Create the team_organization table
                db.session.execute(text("""
                CREATE TABLE team_organization (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    slug VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    logo VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """))
                db.session.commit()
            
            # Check if default team exists
            result = db.session.execute(text("SELECT id FROM team_organization WHERE slug = 'default-team'")).fetchone()
            
            if not result:
                print_status("Creating default team organization...")
                # Create default team
                db.session.execute(text("""
                INSERT INTO team_organization (name, slug, description, created_at) 
                VALUES ('Default Team', 'default-team', 'Default team created during migration', CURRENT_TIMESTAMP)
                """))
                db.session.commit()
            
            # Get the default team ID
            default_team_id = db.session.execute(text("SELECT id FROM team_organization WHERE slug = 'default-team'")).fetchone()[0]
            print_status(f"Default team ID: {default_team_id}")
            
            # List of tables to add team_organization_id to
            tables = [
                'user', 'player', 'drill', 'tournament', 'game', 'session_plan',
                'fitness_metric', 'fitness_record', 'clip', 'clip_tag',
                'line_template', 'line_template_player', 'gameday_event', 'gameday_player_stats',
                'attendance', 'session_rsvp', 'session_component', 'saved_drill',
                'scouting_report', 'opponent_player', 'scouting_clip', 'player_point_stats',
                'export_log'
            ]
            
            # Add team_organization_id to tables if it doesn't exist
            for table in tables:
                try:
                    # Check if the table exists
                    if table in inspector.get_table_names():
                        # Check if the column already exists
                        has_column = check_column_exists(table, 'team_organization_id')
                        
                        if not has_column:
                            print_status(f"Adding team_organization_id to {table}...")
                            db.session.execute(text(f"""
                            ALTER TABLE "{table}" ADD COLUMN team_organization_id INTEGER REFERENCES team_organization(id)
                            """))
                            
                            # Update all records to use the default team
                            db.session.execute(text(f"""
                            UPDATE "{table}" SET team_organization_id = {default_team_id} WHERE team_organization_id IS NULL
                            """))
                            print_status(f"Updated {table} with default team ID")
                except Exception as e:
                    print_status(f"Error processing table {table}: {e}")
                    # Continue with other tables even if one fails
            
            db.session.commit()
            print_status("Team organization setup completed successfully!")
            
        except Exception as e:
            print_status(f"Error during team organization setup: {str(e)}")
            db.session.rollback()
            sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Database management tool')
    parser.add_argument('action', choices=['reset', 'upgrade', 'add_stat_taker', 'add_team_org'], 
                      help='Action to perform: reset (full database reset), upgrade (migrate user roles), add_stat_taker (add stat taker role), or add_team_org (add team organization)')
    
    args = parser.parse_args()
    
    if args.action == 'reset':
        reset_database()
    elif args.action == 'upgrade':
        migrate_user_roles()
        add_team_organization()  # Add this line to include team organization setup during upgrade
    elif args.action == 'add_stat_taker':
        add_stat_taker_role()
    elif args.action == 'add_team_org':
        add_team_organization()
