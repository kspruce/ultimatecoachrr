"""Cached wrappers around the stats calculations."""
from app import cache
from app.models.player import Player
from app.models.game import Game
from app.utils.team_filter import get_current_team_id

from app.stats.formulas import calculate_per_from_stats, games_to_tuple
from app.stats.players import get_player_base_stats
from app.stats.team import calculate_team_averages


def get_cached_team_averages(games=None):
    """Get team averages with Flask-Caching (15-minute TTL)."""
    team_id = get_current_team_id()
    game_ids = games_to_tuple(games) if games else None
    return _cached_team_averages(team_id, game_ids)

@cache.memoize(timeout=900)  # 15 minutes
def _cached_team_averages(team_id, game_ids_tuple):
    """Internal cached worker — keyed by team_id + sorted game IDs."""
    if game_ids_tuple:
        games = Game.query.filter(Game.id.in_(game_ids_tuple)).all()
    else:
        games = None
    return calculate_team_averages(games)

@cache.memoize(timeout=600)  # 10 minutes
def get_cached_player_base_stats(player_id, game_ids_tuple=None, team_id=None):
    """Cached version of player base stats (Flask-Caching, 10-minute TTL)."""
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=team_id
    ).first()

    if not player:
        return {}

    if game_ids_tuple:
        games = Game.query.filter(
            Game.id.in_(game_ids_tuple),
            Game.team_organization_id == team_id
        ).all()
    else:
        games = None

    return get_player_base_stats(player, games)

def calculate_per(player, games=None, team_avgs=None):
    """
    Standardized PER calculation with optimizations
    """
    # Use cached stats if possible
    game_ids_tuple = games_to_tuple(games)
    stats = get_cached_player_base_stats(player.id, game_ids_tuple, get_current_team_id())
    
    # Use the optimized function that works with pre-loaded stats
    return calculate_per_from_stats(stats, team_avgs)
