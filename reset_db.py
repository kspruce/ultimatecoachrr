from app import create_app, db
import os

app = create_app()

def reset_database():
    with app.app_context():
        # Drop all tables in the correct order
        try:
            # Get inspector to find foreign keys
            inspector = db.inspect(db.engine)
            
            # Disable foreign key checks for PostgreSQL
            db.session.execute('SET CONSTRAINTS ALL DEFERRED')
            
            # Drop all tables
            db.session.execute('DROP SCHEMA public CASCADE')
            db.session.execute('CREATE SCHEMA public')
            
            # Grant privileges back
            db.session.execute('GRANT ALL ON SCHEMA public TO postgres')
            db.session.execute('GRANT ALL ON SCHEMA public TO public')
            
            print("Dropped all tables")
            
            # Create all tables
            db.create_all()
            print("Created all tables from scratch")
            
            # Create admin user first
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
            
            # Create test players
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
                
        except Exception as e:
            print(f"Error during database reset: {str(e)}")
            db.session.rollback()
            raise
        finally:
            # Re-enable foreign key checks
            db.session.execute('SET CONSTRAINTS ALL IMMEDIATE')
            db.session.commit()

if __name__ == "__main__":
    try:
        reset_database()
        print("Database reset com
