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
from sqlalchemy import text
import os

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
            
            # The rest of your function remains the same...
            # Create admin user
            admin = User(username='admin', email='admin@example.com', is_admin=True)
            admin.set_password('password')
            db.session.add(admin)
            
            # Create bonus user
            bonus = User(username='bonus', email='bonus@example.com', is_admin=False)
            bonus.set_password('bonusboys')
            db.session.add(bonus)
            
            # Create bonus user
            etaylor = User(username='etaylor', email='et@example.com', is_admin=True)
            etaylor.set_password('Taylor35')
            db.session.add(etaylor)
            
            # Create bonus user
            cspearing = User(username='cspearing', email='cs@example.com', is_admin=True)
            cspearing.set_password('Spearing1')
            db.session.add(cspearing)
            
            # Create bonus user
            bleung = User(username='bleung', email='bl@example.com', is_admin=True)
            bleung.set_password('Leung18')
            db.session.add(bleung)
            
            db.session.commit()
            print_status("Created admin, captains and bonus users")

            # Add test players
            test_players = [
                # Your player data remains the same...
                {"name": "Camilla Spearing", "jersey_number": "1", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "O"},
                # ... rest of your players
            ]

            for player_data in test_players:
                player = Player(**player_data)
                db.session.add(player)
            
            db.session.commit()
            print_status(f"Added {len(test_players)} test players")

            # Create theory sections
            from app.models.theory import TheorySection
            sections = [
                {'name': 'Defense', 'slug': 'defense', 
                 'description': 'Master defensive techniques including footwork, positioning, forcing, and guarding resets.', 'order': 1},
                {'name': 'Throwing', 'slug': 'throwing', 
                 'description': 'Perfect your throwing technique: release points, angles and tilts, give and go, break side throws.', 'order': 2},
                {'name': 'Cutting', 'slug': 'cutting', 
                 'description': 'Learn cutting types, techniques, deep cutting, aerial contests, and triple threat positioning.', 'order': 3},
                {'name': 'Handler Offense', 'slug': 'handler-offense', 
                 'description': 'Develop handler movement: dump swing, resets, moment of attack, give-go offense, dishy huck, three handler offense.', 'order': 4}
            ]

            for section_data in sections:
                section = TheorySection(**section_data)
                db.session.add(section)

            db.session.commit()
            print_status("Created theory sections")

            # The rest of your function remains the same...

            print_status("\nDatabase reset completed successfully!")

        except Exception as e:
            print_status(f"Error: {str(e)}")
            db.session.rollback()
            sys.exit(1)

if __name__ == "__main__":
    reset_database()
