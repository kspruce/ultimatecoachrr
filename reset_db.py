from app import create_app, db
# Import models directly to ensure they're registered
from app.models.point import Point, LineUp
from app.models.event import Event, Pull
from cutting_skill_fixed import CuttingSkill  # Import our new model
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
            from app.models.user import User
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
            from app.models.player import Player
            test_players = [
                {"name": "Camilla Spearing", "jersey_number": "1", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "O"},
                {"name": "Bon Leung", "jersey_number": "18", "position": "hybrid", "gender": "male", "gender_match": "male", "team": "Team A", "line_preference": "D"},
                {"name": "Ed Taylor", "jersey_number": "35", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A", "line_preference": "O"},
                {"name": "Aleksandra Marszalek", "jersey_number": "11", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "O"},
                {"name": "Alexandra Weinberg", "jersey_number": "43", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "D"},
                {"name": "Kate Mitrofanov", "jersey_number": "65", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "D"},
                {"name": "Roan Talbut", "jersey_number": "73", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "D"},
                {"name": "Sophie Wharton", "jersey_number": "25", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "D"},
                {"name": "Charlie Galloway", "jersey_number": "50", "position": "hybrid", "gender": "male", "gender_match": "male", "team": "Team A", "line_preference": "O"},
                {"name": "Chung Leung", "jersey_number": "21", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A", "line_preference": "D"},
                {"name": "Kieran Spruce", "jersey_number": "22", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A", "line_preference": "D"},
                {"name": "Siôn Regan", "jersey_number": "9", "position": "handler", "gender": "male", "gender_match": "male", "team": "Team A", "line_preference": "O"},
                {"name": "Milan Liu", "jersey_number": "59", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "O"},
                {"name": "Christina Athanasiou", "jersey_number": "12", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "D"},
                {"name": "Matt Butler", "jersey_number": "10", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A", "line_preference": "D"},
                {"name": "Alan Sun", "jersey_number": "16", "position": "hybrid", "gender": "male", "gender_match": "male", "team": "Team A", "line_preference": "D"},
                {"name": "Patrick Moore", "jersey_number": "13", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A", "line_preference": "O"},
                {"name": "Sophia Pym", "jersey_number": "90", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "D"},
                {"name": "Adam Zafri", "jersey_number": "80", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team A", "line_preference": "D"},
                {"name": "Nour El Sheikh", "jersey_number": "15", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "D"},
                {"name": "Laura Coleman", "jersey_number": "6", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team A", "line_preference": "O"},
                {"name": "Callum Bennfors", "jersey_number": "51", "position": "handler", "gender": "male", "gender_match": "male", "team": "Team A", "line_preference": "D"},
                {"name": "Irma Ostervall", "jersey_number": "17", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "Team B", "line_preference": "O"},
                {"name": "Ali Thomas", "jersey_number": "", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "Team B", "line_preference": "D"},
                {"name": "Enzia Schnyder", "jersey_number": "", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team B", "line_preference": "O"},
                {"name": "Suze Kurska", "jersey_number": "2", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team B", "line_preference": "D"},
                {"name": "Yousef Abouzeid", "jersey_number": "20", "position": "handler", "gender": "male", "gender_match": "male", "team": "Team B", "line_preference": "D"},
                {"name": "Regina Tandu", "jersey_number": "5", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "Team B", "line_preference": "O"},
                {"name": "Annie Ford", "jersey_number": "26", "position": "cutter", "gender": "female", "gender_match": "female", "team": "Team B", "line_preference": "D"},
                {"name": "Alice Logan", "jersey_number": "81", "position": "hybrid", "gender": "female", "gender_match": "female", "team": "Team B", "line_preference": "O"},
                {"name": "Tom Cliff", "jersey_number": "47", "position": "cutter", "gender": "male", "gender_match": "male", "team": "Team B", "line_preference": "O"},
                {"name": "Vix Willby", "jersey_number": "7", "position": "handler", "gender": "female", "gender_match": "female", "team": "Team B", "line_preference": "O"},
                {"name": "Jack Chuang", "jersey_number": "", "position": "handler", "gender": "male", "gender_match": "male", "team": "Team B", "line_preference": "D"},
                {"name": "Gavin Buddle", "jersey_number": "30", "position": "hybrid", "gender": "male", "gender_match": "male", "team": "Team B", "line_preference": "O"},
                {"name": "Kai Meller", "jersey_number": "28", "position": "handler", "gender": "male", "gender_match": "male", "team": "Team B", "line_preference": "O"},
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

            # Create some default clip tags
            from app.models.clip import ClipTag
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
            
            # Create Moooxed tournament
            from app.models.tournament import Tournament
            tournament = Tournament(
                name="Moooxed",
                start_date=datetime(2025, 6, 7),
                end_date=datetime(2025, 6, 8),
                location="London"
            )
            db.session.add(tournament)
            db.session.commit()
            print_status("Created Moooxed tournament")
            
            # Create games for the tournament
            from app.models.game import Game
            games = [
                # Day 1 - June 7, 2025
                {
                    "date": datetime(2025, 6, 7),
                    "opponent": "Brixton",
                    "our_score": 15,
                    "their_score": 7,
                    "tournament_id": tournament.id,
                    "youtube_link": None,
                    "notes": "First game of the tournament"
                },
                {
                    "date": datetime(2025, 6, 7),
                    "opponent": "Cambridge Mixed Ultimate A",
                    "our_score": 15,
                    "their_score": 4,
                    "tournament_id": tournament.id,
                    "youtube_link": None,
                    "notes": "Second game of the tournament"
                },
                {
                    "date": datetime(2025, 6, 7),
                    "opponent": "Curve Vector",
                    "our_score": 12,
                    "their_score": 8,
                    "tournament_id": tournament.id,
                    "youtube_link": None,
                    "notes": "Third game of the tournament"
                },
                # Day 2 - June 8, 2025
                {
                    "date": datetime(2025, 6, 8),
                    "opponent": "Reading2",
                    "our_score": 14,
                    "their_score": 4,
                    "tournament_id": tournament.id,
                    "youtube_link": None,
                    "notes": "Fourth game of the tournament"
                },
                {
                    "date": datetime(2025, 6, 8),
                    "opponent": "Bristol",
                    "our_score": 13,
                    "their_score": 8,
                    "tournament_id": tournament.id,
                    "youtube_link": None,
                    "notes": "Fifth game of the tournament"
                },
                {
                    "date": datetime(2025, 6, 8),
                    "opponent": "Curve Vector",
                    "our_score": 13,
                    "their_score": 9,
                    "tournament_id": tournament.id,
                    "youtube_link": None,
                    "notes": "Final game of the tournament"
                }
            ]
            
            for game_data in games:
                game = Game(**game_data)
                db.session.add(game)
                
            db.session.commit()
            print_status(f"Added {len(games)} games to the Moooxed tournament")

            print_status("\nDatabase reset completed successfully!")

        except Exception as e:
            print_status(f"Error: {str(e)}")
            db.session.rollback()
            sys.exit(1)

if __name__ == "__main__":
    reset_database()