from app import create_app, db
from flask_migrate import upgrade

app = create_app()

def reset_database():
    with app.app_context():
        # Run migrations
        upgrade()
        print("Applied migrations")
        
        # Create admin user
        from app.models.user import User
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                email='admin@example.com',
                is_admin=True
            )
            admin.set_password('password')
            db.session.add(admin)
            db.session.commit()
            print("Created admin user (username: admin, password: password)")
        
        # Add test data
        from app.models.player import Player
        if Player.query.count() == 0:
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

if __name__ == "__main__":
    try:
        reset_database()
        print("Database reset complete!")
    except Exception as e:
        print(f"Error: {str(e)}")
