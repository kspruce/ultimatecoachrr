from app import create_app, db
from sqlalchemy import text, event
from sqlalchemy.orm import configure_mappers, mapper
from app.models import *  # Import all models from __init__.py
from datetime import datetime
import sys

app = create_app()

def print_status(message):
    """Helper function to print status messages"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

# Configure all mappers before creating tables
@event.listens_for(mapper, 'after_configured')
def receive_after_configured():
    print_status("SQLAlchemy mappers configured")

def reset_database():
    """Reset and initialize the database"""
    with app.app_context():
        try:
            print_status("Starting database reset...")
            
            # Configure mappers first
            configure_mappers()
            
            # Drop and recreate all tables
            db.drop_all()
            print_status("Dropped all tables")
            
            db.create_all()
            print_status("Created all tables")

            # Create admin user
            admin = User(username='admin', email='admin@example.com', is_admin=True)
            admin.set_password('password')
            db.session.add(admin)
            
            # Create bonus user
            bonus = User(username='bonus', email='bonus@example.com', is_admin=False)
            bonus.set_password('bonusboys')
            db.session.add(bonus)
            
            db.session.commit()
            print_status("Created admin and bonus users")

            # Add test players
            test_players = [
                {"name": "Alice", "jersey_number": "1", "position": "handler", "gender": "female", "gender_match": "female", "team": "team1"},
                {"name": "Bob", "jersey_number": "2", "position": "cutter", "gender": "male", "gender_match": "male", "team": "team1"},
                {"name": "Charlie", "jersey_number": "3", "position": "handler", "gender": "male", "gender_match": "male", "team": "team1"},
                {"name": "David", "jersey_number": "4", "position": "cutter", "gender": "male", "gender_match": "male", "team": "team1"},
                {"name": "Eve", "jersey_number": "5", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "team1"},
                {"name": "Jona", "jersey_number": "8", "position": "cutter", "gender": "female", "gender_match": "female", "team": "team1"},
                {"name": "Mallory", "jersey_number": "10", "position": "handler", "gender": "female", "gender_match": "female", "team": "team1"},
            ]

            for player_data in test_players:
                player = Player(**player_data)
                db.session.add(player)
            
            db.session.commit()
            print_status(f"Added {len(test_players)} test players")

            # Create theory sections
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

            # Create a test tournament
            tournament = Tournament(
                name="Test Tournament 2025",
                start_date=datetime.now().date(),
                location="Test Location",
                season="2025"
            )
            db.session.add(tournament)
            db.session.commit()
            print_status("Created test tournament")

            # Verify the database
            print_status("\nVerifying database contents:")
            
            users = User.query.all()
            print_status("\nUsers:")
            for user in users:
                print_status(f"- {user.username} (Admin: {user.is_admin})")

            players = Player.query.all()
            print_status("\nPlayers:")
            for player in players:
                print_status(f"- {player.name} (#{player.jersey_number})")

            sections = TheorySection.query.all()
            print_status("\nTheory Sections:")
            for section in sections:
                print_status(f"- {section.name} (slug: {section.slug})")

            tournaments = Tournament.query.all()
            print_status("\nTournaments:")
            for tournament in tournaments:
                print_status(f"- {tournament.name} ({tournament.season})")

            print_status("\nDatabase reset completed successfully!")

        except Exception as e:
            print_status(f"Error: {str(e)}")
            db.session.rollback()
            sys.exit(1)

if __name__ == "__main__":
    reset_database()
