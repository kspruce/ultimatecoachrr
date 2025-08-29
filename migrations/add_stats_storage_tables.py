"""
Migration script to add stats storage tables to the database
"""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from app import create_app, db
from app.models.stats_storage import IndexStats, TeamStats, GameStats, PlayerStats

def run_migration():
    """Run the migration to add stats storage tables"""
    app = create_app()
    with app.app_context():
        # Create the tables if they don't exist
        db.create_all()
        
        # Check if the tables were created successfully
        tables_created = []
        
        if IndexStats.__tablename__ in db.metadata.tables:
            tables_created.append(IndexStats.__tablename__)
        
        if TeamStats.__tablename__ in db.metadata.tables:
            tables_created.append(TeamStats.__tablename__)
        
        if GameStats.__tablename__ in db.metadata.tables:
            tables_created.append(GameStats.__tablename__)
        
        if PlayerStats.__tablename__ in db.metadata.tables:
            tables_created.append(PlayerStats.__tablename__)
        
        print(f"Stats storage tables created successfully: {', '.join(tables_created)}")
        
        # Create indexes for better performance
        try:
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_index_stats_team_org ON index_stats (team_organization_id)')
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_index_stats_version ON index_stats (version)')
            
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_team_stats_team_org ON team_stats (team_organization_id)')
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_team_stats_version ON team_stats (version)')
            
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_game_stats_game ON game_stats (game_id)')
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_game_stats_team_org ON game_stats (team_organization_id)')
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_game_stats_version ON game_stats (version)')
            
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_player_stats_player ON player_stats (player_id)')
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_player_stats_game ON player_stats (game_id)')
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_player_stats_team_org ON player_stats (team_organization_id)')
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_player_stats_version ON player_stats (version)')
            
            db.session.commit()
            print("Indexes created successfully")
        except Exception as e:
            db.session.rollback()
            print(f"Error creating indexes: {str(e)}")

if __name__ == "__main__":
    run_migration()