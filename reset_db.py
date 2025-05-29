from app import create_app, db
from sqlalchemy import text

app = create_app()

def reset_database():
    with app.app_context():
        # Execute raw SQL commands
        commands = [
            "DROP SCHEMA public CASCADE",
            "CREATE SCHEMA public",
            "GRANT ALL ON SCHEMA public TO public",  # Remove postgres user grant
            """
            CREATE TABLE "user" (
                id SERIAL PRIMARY KEY,
                username VARCHAR(64) UNIQUE NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(128),
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE player (
                id SERIAL PRIMARY KEY,
                name VARCHAR(64) NOT NULL,
                jersey_number INTEGER,
                position VARCHAR(20),
                gender VARCHAR(20),
                gender_match VARCHAR(20),
                team VARCHAR(64),
                user_id INTEGER REFERENCES "user"(id)
            )
            """
        ]
        
        # Execute each command
        for command in commands:
            try:
                db.session.execute(text(command))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"Warning: Command failed: {str(e)}")
                # Continue with next command
                continue
        
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
        
        # Add test data
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

if __name__ == "__main__":
    try:
        reset_database()
        print("Database reset complete!")
    except Exception as e:
        print(f"Error: {str(e)}")
