import sys
import os
from datetime import datetime

# Disable Discord integration if needed
os.environ['DISCORD_ENABLED'] = 'False'

# Import app and models using the same pattern as db_manager.py
from app import create_app, db
# Import the OffSeasonWorkout model - adjust the import path as needed
from app.models.workout import OffSeasonWorkout  # Modify this path based on your actual model location

# Create app instance
app = create_app()

def print_status(message):
    """Helper function to print status messages"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def categorize_workouts():
    """Categorize workouts that don't have a category assigned"""
    with app.app_context():
        try:
            print_status("Starting workout categorization...")
            
            # Get all workouts without a category
            workouts = OffSeasonWorkout.query.filter(OffSeasonWorkout.workout_category == None).all()
            
            if not workouts:
                print_status("No uncategorized workouts found.")
                return
                
            print_status(f"Found {len(workouts)} uncategorized workouts.")
            
            for workout in workouts:
                # Categorize based on workout_type
                if workout.workout_type in ['Strength', 'Power']:
                    workout.workout_category = 'Strength'
                elif workout.workout_type in ['Throwing', 'Technical']:
                    workout.workout_category = 'Skills'
                elif workout.workout_type in ['Endurance', 'Speed', 'Agility', 'Recovery']:
                    workout.workout_category = 'Conditioning'
                else:
                    # Default category
                    workout.workout_category = 'Strength'
            
            # Commit changes
            db.session.commit()
            print_status(f"Successfully categorized {len(workouts)} workouts")
            
        except Exception as e:
            print_status(f"Error during workout categorization: {str(e)}")
            db.session.rollback()
            sys.exit(1)

if __name__ == "__main__":
    categorize_workouts()
