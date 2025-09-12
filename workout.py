import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from off_season import app, db, OffSeasonWorkout

def categorize_workouts():
    with app.app_context():
        # Get all workouts without a category
        workouts = OffSeasonWorkout.query.filter(OffSeasonWorkout.workout_category == None).all()
        
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
        print(f"Categorized {len(workouts)} workouts")

if __name__ == "__main__":
    categorize_workouts()