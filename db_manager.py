from app import create_app, db
# Import models directly from app.models
from app.models.user import User
from app.models.player import Player
from app.models.tournament import Tournament
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.event import Event, Pull
from app.models.clip import Clip, ClipTag
from app.models.session import SessionPlan, SessionComponent, SavedDrill, Attendance
from app.models.cutting_skill import CuttingSkill
from app.models.theory import TheorySection
from app.models.fitness import FitnessMetric, FitnessRecord
from app.models.gameday import LineTemplate, LineTemplatePlayer, GameDayEvent, GameDayPlayerStats  # Add these imports
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
            
            # Create admin user
            admin = User(username='admin', email='admin@example.com', role='admin')
            admin.set_password('password')
            db.session.add(admin)
            
            # Create bonus user
            bonus = User(username='bonus', email='bonus@example.com', role='player')
            bonus.set_password('bonusboys')
            db.session.add(bonus)
            
            # Create captain users with coach role
            etaylor = User(username='etaylor', email='et@example.com', role='coach')
            etaylor.set_password('Taylor35')
            db.session.add(etaylor)
            
            cspearing = User(username='cspearing', email='cs@example.com', role='coach')
            cspearing.set_password('Spearing1')
            db.session.add(cspearing)
            
            bleung = User(username='bleung', email='bl@example.com', role='coach')
            bleung.set_password('Leung18')
            db.session.add(bleung)
            
            # Create a stat taker user
            stat_taker = User(username='stats', email='stats@example.com', role='stat_taker')
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Database management tool')
    parser.add_argument('action', choices=['reset', 'upgrade', 'add_stat_taker'], 
                        help='Action to perform: reset (full database reset), upgrade (migrate user roles), or add_stat_taker (add stat taker role)')
    
    args = parser.parse_args()
    
    if args.action == 'reset':
        reset_database()
    elif args.action == 'upgrade':
        migrate_user_roles()
    elif args.action == 'add_stat_taker':
        add_stat_taker_role()
