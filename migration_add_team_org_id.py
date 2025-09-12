"""
Migration script to add team_organization_id to weekly_workout_completion table
"""
from app import create_app, db
from flask_migrate import Migrate
from sqlalchemy import text

def run_migration():
    """Run the migration to add team_organization_id column"""
    app = create_app()
    
    with app.app_context():
        # Check if the column already exists
        result = db.session.execute(text("""
            SELECT COUNT(*) 
            FROM information_schema.columns 
            WHERE table_name='weekly_workout_completion' 
            AND column_name='team_organization_id'
        """))
        
        if result.scalar() == 0:
            print("Adding team_organization_id column to weekly_workout_completion table...")
            
            # Add the column
            db.session.execute(text("""
                ALTER TABLE weekly_workout_completion 
                ADD COLUMN team_organization_id INTEGER
            """))
            
            # Add foreign key constraint
            db.session.execute(text("""
                ALTER TABLE weekly_workout_completion 
                ADD CONSTRAINT fk_weekly_completion_team_org 
                FOREIGN KEY (team_organization_id) 
                REFERENCES team_organization(id)
            """))
            
            # Update existing records to use the team_organization_id from the related phase
            db.session.execute(text("""
                UPDATE weekly_workout_completion wwc
                SET team_organization_id = (
                    SELECT team_organization_id 
                    FROM off_season_phase 
                    WHERE id = wwc.phase_id
                )
            """))
            
            db.session.commit()
            print("Migration completed successfully!")
        else:
            print("Column team_organization_id already exists in weekly_workout_completion table.")

if __name__ == "__main__":
    run_migration()