from app.models.stats import PlayerStats, TeamStats
from flask_login import current_user

def get_current_team_id():
    """Temporary function until proper team_utils module is created"""
    if current_user and hasattr(current_user, 'team_organization_id'):
        return current_user.team_organization_id
    return None

def get_player_stats_from_db(player_id, game_id=None, tournament_id=None, season=None):
    """
    Retrieve pre-calculated player statistics from the database.
    
    Args:
        player_id: ID of the player
        game_id: Optional game ID for game-specific stats
        tournament_id: Optional tournament ID for tournament-specific stats
        season: Optional season name for season-specific stats
        
    Returns:
        Dictionary of player statistics or None if not found
    """
    query = PlayerStats.query.filter_by(player_id=player_id)
    
    if game_id:
        query = query.filter_by(game_id=game_id)
    elif tournament_id:
        query = query.filter_by(tournament_id=tournament_id, game_id=None)
    elif season:
        query = query.filter_by(season=season, tournament_id=None, game_id=None)
    else:
        # Get overall stats (no specific game, tournament, or season)
        query = query.filter_by(game_id=None, tournament_id=None, season=None)
    
    stats = query.first()
    
    if stats:
        # Convert SQLAlchemy model to dictionary
        return {c.name: getattr(stats, c.name) for c in stats.__table__.columns}
    
    return None

def get_team_summary_from_db(game_id=None, tournament_id=None, season=None):
    """
    Retrieve pre-calculated team statistics from the database.
    
    Args:
        game_id: Optional game ID for game-specific stats
        tournament_id: Optional tournament ID for tournament-specific stats
        season: Optional season name for season-specific stats
        
    Returns:
        Dictionary of team statistics or None if not found
    """
    team_org_id = get_current_team_id()
    if not team_org_id:
        return None
        
    query = TeamStats.query.filter_by(team_organization_id=team_org_id)
    
    if game_id:
        query = query.filter_by(game_id=game_id)
    elif tournament_id:
        query = query.filter_by(tournament_id=tournament_id, game_id=None)
    elif season:
        query = query.filter_by(season=season, tournament_id=None, game_id=None)
    else:
        # Get overall stats (no specific game, tournament, or season)
        query = query.filter_by(game_id=None, tournament_id=None, season=None)
    
    stats = query.first()
    
    if stats:
        # Convert SQLAlchemy model to dictionary
        return {c.name: getattr(stats, c.name) for c in stats.__table__.columns}
    
    return None

def get_cached_team_averages(games):
    """
    Get team averages, either from cache or calculate them.
    This is a helper function to avoid recalculating team averages multiple times.
    
    Args:
        games: List of Game objects
        
    Returns:
        Dictionary of team average statistics
    """
    # In a real implementation, you might want to use a proper caching mechanism
    # For now, we'll just calculate it each time
    from app.utils.stats_calculator import calculate_team_averages
    return calculate_team_averages(games)
