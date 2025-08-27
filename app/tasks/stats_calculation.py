from app import db, create_app
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.stats import PlayerStats, TeamStats
# IMPORTANT: We will move the calculation logic from your routes file to here.
# For now, let's assume they are available to be imported.
from app.routes.stats import get_player_base_stats, calculate_team_summary, calculate_per, calculate_team_averages
from datetime import datetime

def run_stats_recalculation_task():
    """
    This is the main task to be run by a scheduler.
    It finds all 'dirty' stats records and recalculates them.
    """
    app = create_app()
    with app.app_context():
        # Recalculate dirty player stats
        dirty_player_stats = PlayerStats.query.filter_by(is_dirty=True).all()
        for record in dirty_player_stats:
            player = Player.query.get(record.player_id)
            if not player: continue

            # Determine scope
            games = None
            if record.game_id:
                games = [Game.query.get(record.game_id)]
            elif record.tournament_id:
                games = Game.query.filter_by(tournament_id=record.tournament_id).all()
            elif record.season:
                tourney_ids = [t.id for t in Tournament.query.filter_by(season=record.season).all()]
                games = Game.query.filter(Game.tournament_id.in_(tourney_ids)).all()
            
            # Recalculate
            stats_dict = get_player_base_stats(player, games)
            team_avgs = calculate_team_averages(games)
            per = calculate_per(player, games, team_avgs)

            # Update record
            record.points_played = stats_dict.get('points_played', 0)
            # ... update all other fields from stats_dict ...
            record.per = per
            record.is_dirty = False
            record.last_calculated = datetime.utcnow()
        
        db.session.commit()
        print(f"Recalculated {len(dirty_player_stats)} player stat records.")

        # Recalculate dirty team stats
        dirty_team_stats = TeamStats.query.filter_by(is_dirty=True).all()
        for record in dirty_team_stats:
            # Determine scope
            games = None
            if record.game_id:
                games = [Game.query.get(record.game_id)]
            # ... similar logic for tournament and season ...

            # Recalculate
            summary = calculate_team_summary(games)

            # Update record
            record.wins = summary.get('wins', 0)
            # ... update all other fields from summary ...
            record.is_dirty = False
            record.last_calculated = datetime.utcnow()

        db.session.commit()
        print(f"Recalculated {len(dirty_team_stats)} team stat records.")
