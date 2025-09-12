import sys
import os
from datetime import datetime

# Disable Discord integration if needed
os.environ['DISCORD_ENABLED'] = 'False'

# Import app and models
from app import create_app, db
from sqlalchemy import text

# Create app instance
app = create_app()

def print_status(message):
    """Helper function to print status messages"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def add_workout_category_column():
    """Add workout_category column to off_season_workout table"""
    with app.app_context():
        try:
            print_status("Adding workout_category column to off_season_workout table...")
            
            # Add the column if it doesn't exist
            db.session.execute(
                text("ALTER TABLE off_season_workout ADD COLUMN IF NOT EXISTS workout_category VARCHAR(50)")
            )
            
            db.session.commit()
            print_status("Successfully added workout_category column")
            
        except Exception as e:
            print_status(f"Error adding column: {str(e)}")
            db.session.rollback()
            sys.exit(1)

if __name__ == "__main__":
    add_workout_category_column()
