from app import create_app, db
import os
import time
import sqlite3

app = create_app()

with app.app_context():
    # Get the database path
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    
    # Check if the database file exists
    if os.path.exists(db_path):
        print(f"Backing up database to {db_path}.bak")
        # Create a backup
        import shutil
        try:
            shutil.copy2(db_path, f"{db_path}.bak")
        except Exception as e:
            print(f"Warning: Could not create backup: {str(e)}")
        
        # Try to delete the database file
        try:
            # Close all connections to the database
            db.session.close()
            db.engine.dispose()
            
            # Wait a moment for connections to close
            time.sleep(1)
            
            # Try to delete the file
            os.remove(db_path)
            print(f"Deleted database file: {db_path}")
        except Exception as e:
            print(f"Warning: Could not delete database file: {str(e)}")
            print("Attempting to recreate tables in the existing database...")
            
            # Try to drop all tables instead
            try:
                # Connect directly to the database
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Get a list of all tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                
                # Drop each table
                for table in tables:
                    if table[0] != 'sqlite_sequence':  # Skip the sqlite_sequence table
                        cursor.execute(f"DROP TABLE IF EXISTS {table[0]};")
                
                conn.commit()
                conn.close()
                print("Successfully dropped all tables.")
            except Exception as e:
                print(f"Warning: Could not drop tables: {str(e)}")
                print("Continuing with table creation anyway...")
    
    # Create all tables
    db.create_all()
    print("Created all tables from scratch")
    
    #create a team of 7 players
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
        db.session.commit()
        print("Added test players.")   
    
    # Create a user for testing
    from app.models.user import User
    if not User.query.filter_by(username='admin').first():
        user = User(
            username='admin', 
            email='admin@example.com', 
            is_admin=True  # Use is_admin instead of role
        )
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        print("Created admin user (username: admin, password: password)")
    
    print("Database reset complete!")
