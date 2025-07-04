from app import create_app, db
from app.models import *
from datetime import datetime
import sys

app = create_app()

def print_status(message):
    """Helper function to print status messages"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def reset_database():
    """Reset and initialize the database"""
    with app.app_context():
        try:
            print_status("Starting database reset...")
            
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
                {"name": "Camilla Spearing", "jersey_number": "1", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team A"},
                {"name": "Bon Leung", "jersey_number": "18", "position": "hybrid", "gender": "male", "gender_match": "male", "team": "Team A"},
                {"name": "Ed Taylor", "jersey_number": "35", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A"},
                {"name": "Aleksandra Marszalek", "jersey_number": "11", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team A"},
                {"name": "Alexandra Weinberg", "jersey_number": "43", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team A"},
                {"name": "Kate Mitrofanov", "jersey_number": "65", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A"},
                {"name": "Roan Talbut", "jersey_number": "73", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "Team A"},
                {"name": "Sophie Wharton", "jersey_number": "25", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A"},
                {"name": "Charlie Galloway", "jersey_number": "50", "position": "hybrid", "gender": "male", "gender_match": "male", "team": "Team A"},
                {"name": "Chung Leung", "jersey_number": "21", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A"},
                {"name": "Kieran Spruce", "jersey_number": "22", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A"},
                {"name": "Siôn Regan", "jersey_number": "9", "position": "handler", "gender": "male", "gender_match": "male", "team": "Team A"},
                {"name": "Milan Liu", "jersey_number": "59", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A"},
                {"name": "Christina Athanasiou", "jersey_number": "12", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A"},
                {"name": "Matt Butler", "jersey_number": "10", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A"},
                {"name": "Alan Sun", "jersey_number": "16", "position": "hybrid", "gender": "male", "gender_match": "male", "team": "Team A"},
                {"name": "Patrick Moore", "jersey_number": "13", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A"},
                {"name": "Sophia Pym", "jersey_number": "90", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A"},
                {"name": "Adam Zafri", "jersey_number": "80", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A"},
                {"name": "Nour El Sheikh", "jersey_number": "15", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team A"},
                {"name": "Laura Coleman", "jersey_number": "6", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A"},
                {"name": "Callum Bennfors", "jersey_number": "51", "position": "handler", "gender": "male", "gender_match": "male", "team": "Team A"},
                {"name": "Irma Ostervall", "jersey_number": "17", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "Team B"},
                {"name": "Ali Thomas", "jersey_number": "", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "Team B"},
                {"name": "Enzia Schnyder", "jersey_number": "", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team B"},
                {"name": "Suze Kurska", "jersey_number": "2", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team B"},
                {"name": "Yousef Abouzeid", "jersey_number": "20", "position": "handler", "gender": "male", "gender_match": "male", "team": "Team B"},
                {"name": "Regina Tandu", "jersey_number": "5", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "Team B"},
                {"name": "Annie Ford", "jersey_number": "26", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team B"},
                {"name": "Alice Logan", "jersey_number": "81", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "Team B"},
                {"name": "Tom Cliff", "jersey_number": "47", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team B"},
                {"name": "Vix Willby", "jersey_number": "7", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team B"},
                {"name": "Jack Chuang", "jersey_number": "", "position": "handler", "gender": "male", "gender_match": "male", "team": "Team B"},
                {"name": "Gavin Buddle", "jersey_number": "30", "position": "hybrid", "gender": "male", "gender_match": "male", "team": "Team B"},
                {"name": "Kai Meller", "jersey_number": "28", "position": "handler", "gender": "male", "gender_match": "male", "team": "Team B"},
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

            # Create some default clip tags
            default_tags = [
                {'name': 'Offense', 'category': 'phase'},
                {'name': 'Defense', 'category': 'phase'},
                {'name': 'Goal', 'category': 'outcome'},
                {'name': 'Turnover', 'category': 'outcome'},
            ]

            for tag_data in default_tags:
                tag = ClipTag(**tag_data)
                db.session.add(tag)

            db.session.commit()
            print_status("Created default clip tags")

            print_status("\nDatabase reset completed successfully!")

        except Exception as e:
            print_status(f"Error: {str(e)}")
            db.session.rollback()
            sys.exit(1)

if __name__ == "__main__":
    reset_database()
