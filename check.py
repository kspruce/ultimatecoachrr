from app import create_app, db
from app.models.stats_storage import IndexStats, TeamStats, GameStats, PlayerStats

app = create_app()
with app.app_context():
    # Drop existing tables
    for table_name in ['index_stats', 'team_stats', 'game_stats', 'player_stats']:
        db.session.execute(f'DROP TABLE IF EXISTS {table_name}')
    db.session.commit()
    
    # Create tables with the correct schema
    db.create_all()