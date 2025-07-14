from app import create_app, db
from sqlalchemy import text
from app.models.theory import TheorySection

app = create_app()

def create_initial_sections():
    with app.app_context():
        # Check if sections already exist
        if TheorySection.query.first():
            print("Theory sections already exist, skipping creation.")
            return

        sections = [
            {
                'name': 'Defense',
                'slug': 'defense',
                'description': 'Master defensive techniques including footwork, positioning, forcing, and guarding resets.',
                'order': 1
            },
            {
                'name': 'Throwing',
                'slug': 'throwing',
                'description': 'Perfect your throwing technique: release points, angles and tilts, give and go, break side throws.',
                'order': 2
            },
            {
                'name': 'Cutting',
                'slug': 'cutting',
                'description': 'Learn cutting types, techniques, deep cutting, aerial contests, and triple threat positioning.',
                'order': 3
            },
            {
                'name': 'Handler Offense',
                'slug': 'handler-offense',
                'description': 'Develop handler movement: dump swing, resets, moment of attack, give-go offense, dishy huck, three handler offense.',
                'order': 4
            }
        ]
        
        for section_data in sections:
            section = TheorySection(**section_data)
            db.session.add(section)
        
        try:
            db.session.commit()
            print("Successfully created initial theory sections!")
        except Exception as e:
            db.session.rollback()
            print(f"Error creating theory sections: {str(e)}")

def reset_database():
    with app.app_context():
        # Drop all tables
        db.drop_all()
        
        # Create all tables
        db.create_all()
        
        print("Reset database schema")
        
        # Create admin user
        from app.models.user import User
        admin = User(
            username='admin',
            email='admin@example.com',
            is_admin=True
        )
        admin.set_password('password')
        db.session.add(admin)
        db.session.commit()
        print("Created admin user (username: admin, password: password)")
        
        # Add test players
        from app.models.player import Player
        test_players = [
            Player(name="Alice", jersey_number=1, position="handler", gender="female", gender_match="female", team="team1"),
            Player(name="Bob", jersey_number=2, position="cutter", gender="male", gender_match="male", team="team1"),
            Player(name="Charlie", jersey_number=3, position="handler", gender="male", gender_match="male", team="team1"),
            Player(name="David", jersey_number=4, position="cutter", gender="male", gender_match="male", team="team1"),
            Player(name="Eve", jersey_number=5, position="hybrid", gender="female", gender_match="female", team="team1"),
            Player(name="Jona", jersey_number=8, position="cutter", gender="female", gender_match="female", team="team1"),
            Player(name="Mallory", jersey_number=10, position="handler", gender="female", gender_match="female", team="team1"),
        ]
        
        for player in test_players:
            db.session.add(player)
        
        try:
            db.session.commit()
            print("Added test players.")
        except Exception as e:
            db.session.rollback()
            print(f"Error adding players: {str(e)}")

        # Create theory sections
        create_initial_sections()

def verify_database():
    with app.app_context():
        # Verify users
        from app.models.user import User
        users = User.query.all()
        print("\nVerifying users:")
        for user in users:
            print(f"- {user.username} (Admin: {user.is_admin})")

        # Verify players
        from app.models.player import Player
        players = Player.query.all()
        print("\nVerifying players:")
        for player in players:
            print(f"- {player.name} (#{player.jersey_number})")

        # Verify theory sections
        sections = TheorySection.query.all()
        print("\nVerifying theory sections:")
        for section in sections:
            print(f"- {section.name} (slug: {section.slug})")

if __name__ == "__main__":
    try:
        reset_database()
        print("\nDatabase reset complete!")
        print("\nVerifying database contents:")
        verify_database()
    except Exception as e:
        print(f"Error: {str(e)}")
