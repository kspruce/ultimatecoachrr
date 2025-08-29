"""
Integration code for stats routes to use the stats storage system
"""

# Import the stats storage models
from app.models.stats_storage import IndexStats, TeamStats, GameStats, PlayerStats
import json

# Function to check for saved index stats
def check_saved_index_stats(team_organization_id):
    """Check if there are saved index stats for the current team organization"""
    saved_stats = IndexStats.query.filter_by(
        team_organization_id=team_organization_id
    ).order_by(IndexStats.version.desc()).first()
    
    if saved_stats:
        return saved_stats.stats_data
    return None

# Function to check for saved team stats
def check_saved_team_stats(team_organization_id, filter_params=None):
    """Check if there are saved team stats for the current team organization"""
    query = TeamStats.query.filter_by(
        team_organization_id=team_organization_id
    ).order_by(TeamStats.version.desc())
    
    # If filter parameters are provided, try to match them
    if filter_params:
        query = query.filter(TeamStats.filter_params.contains(filter_params))
    
    saved_stats = query.first()
    if saved_stats:
        return saved_stats.stats_data
    return None

# Function to check for saved game stats
def check_saved_game_stats(game_id, team_organization_id):
    """Check if there are saved game stats for the specified game"""
    saved_stats = GameStats.query.filter_by(
        game_id=game_id,
        team_organization_id=team_organization_id
    ).order_by(GameStats.version.desc()).first()
    
    if saved_stats:
        return saved_stats.stats_data
    return None

# Function to check for saved player stats
def check_saved_player_stats(player_id, team_organization_id, game_id=None, filter_params=None):
    """Check if there are saved player stats for the specified player"""
    query = PlayerStats.query.filter_by(
        player_id=player_id,
        team_organization_id=team_organization_id
    )
    
    if game_id:
        query = query.filter_by(game_id=game_id)
    else:
        query = query.filter_by(game_id=None)
    
    # If filter parameters are provided, try to match them
    if filter_params:
        query = query.filter(PlayerStats.filter_params.contains(filter_params))
    
    saved_stats = query.order_by(PlayerStats.version.desc()).first()
    if saved_stats:
        return saved_stats.stats_data
    return None

# Modified index route function to check for saved stats
def modified_index_route(original_index_function):
    """Decorator to modify the index route to check for saved stats"""
    def wrapper(*args, **kwargs):
        # Get team organization ID from current user
        team_organization_id = get_current_team_id()
        
        # Check if there are saved stats
        saved_stats = check_saved_index_stats(team_organization_id)
        if saved_stats:
            # Use saved stats
            return render_template(
                'stats/index.html',
                **saved_stats,
                is_admin=is_admin(current_user),
                is_coach=is_coach(current_user),
                using_saved_stats=True
            )
        
        # If no saved stats, use the original function
        return original_index_function(*args, **kwargs)
    
    return wrapper

# Modified team stats route function to check for saved stats
def modified_team_stats_route(original_team_stats_function):
    """Decorator to modify the team stats route to check for saved stats"""
    def wrapper(*args, **kwargs):
        # Get team organization ID from current user
        team_organization_id = get_current_team_id()
        
        # Get filter parameters
        season = request.args.get('season', '')
        tournament_id = request.args.get('tournament_id', type=int)
        
        # Create filter params dictionary
        filter_params = {}
        if season:
            filter_params['season'] = season
        if tournament_id:
            filter_params['tournament_id'] = tournament_id
        
        # Check if there are saved stats
        saved_stats = check_saved_team_stats(team_organization_id, filter_params if filter_params else None)
        if saved_stats:
            # Use saved stats
            return render_template(
                'stats/team_stats.html',
                **saved_stats,
                tournaments=Tournament.query.filter_by(team_organization_id=team_organization_id).order_by(Tournament.start_date.desc()).all(),
                seasons=db.session.query(Tournament.season).filter_by(team_organization_id=team_organization_id).distinct().all(),
                selected_tournament=tournament_id,
                selected_season=season,
                using_saved_stats=True
            )
        
        # If no saved stats, use the original function
        return original_team_stats_function(*args, **kwargs)
    
    return wrapper

# Modified game stats route function to check for saved stats
def modified_game_stats_route(original_game_stats_function):
    """Decorator to modify the game stats route to check for saved stats"""
    def wrapper(game_id, *args, **kwargs):
        # Get team organization ID from current user
        team_organization_id = get_current_team_id()
        
        # Check if there are saved stats
        saved_stats = check_saved_game_stats(game_id, team_organization_id)
        if saved_stats:
            # Get the game object
            game = Game.query.filter_by(
                id=game_id,
                team_organization_id=team_organization_id
            ).first_or_404()
            
            # Use saved stats
            return render_template(
                'stats/game_stats.html',
                game=game,
                **saved_stats,
                calculate_impact_score=calculate_impact_score,
                is_admin=is_admin,
                is_coach=is_coach,
                using_saved_stats=True
            )
        
        # If no saved stats, use the original function
        return original_game_stats_function(game_id, *args, **kwargs)
    
    return wrapper

# Modified player stats route function to check for saved stats
def modified_player_stats_route(original_player_stats_function):
    """Decorator to modify the player stats route to check for saved stats"""
    def wrapper(player_id, *args, **kwargs):
        # Get team organization ID from current user
        team_organization_id = get_current_team_id()
        
        # Get filter parameters
        tournament_id = request.args.get('tournament_id', type=int)
        game_id = request.args.get('game_id', type=int)
        
        # Create filter params dictionary
        filter_params = {}
        if tournament_id:
            filter_params['tournament_id'] = tournament_id
        
        # Check if there are saved stats
        saved_stats = check_saved_player_stats(player_id, team_organization_id, game_id, filter_params if filter_params else None)
        if saved_stats:
            # Get the player object
            player = Player.query.filter_by(
                id=player_id,
                team_organization_id=team_organization_id
            ).first_or_404()
            
            # Use saved stats
            return render_template(
                'stats/player_stats.html',
                player=player,
                **saved_stats,
                tournaments=Tournament.query.filter_by(team_organization_id=team_organization_id).order_by(Tournament.start_date.desc()).all(),
                selected_tournament=tournament_id,
                selected_game=game_id,
                using_saved_stats=True
            )
        
        # If no saved stats, use the original function
        return original_player_stats_function(player_id, *args, **kwargs)
    
    return wrapper

# To use these functions, you would modify your routes like this:
"""
@bp.route('/')
@login_required
@modified_index_route
def index():
    # Original index function code here
    ...

@bp.route('/team')
@login_required
@modified_team_stats_route
def team_stats():
    # Original team_stats function code here
    ...

@bp.route('/game/<int:game_id>')
@login_required
@modified_game_stats_route
def game_stats(game_id):
    # Original game_stats function code here
    ...

@bp.route('/player/<int:player_id>')
@login_required
@modified_player_stats_route
def player_stats(player_id):
    # Original player_stats function code here
    ...
"""