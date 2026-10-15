"""Pure stat formulas: no database access."""
from app.models.point import Point, LineUp
from app.utils.team_filter import get_current_team_id



PER_WEIGHTS = {
    'scoring': 0.5,
    'assist': 0.5,
    'turnover': -0.75,
    'defense': 0.75,
    'throw': 0.05,
    'plus_minus': 0.1
}

TURNOVER_EVENTS = {'throwaway', 'drop', 'stall'}

def calculate_unadjusted_per(stats):
    """Calculate raw unadjusted PER without team average adjustments"""
    if stats['points_played'] == 0:
        return 0
    
    # Define weights
    WEIGHTS = PER_WEIGHTS
    
    # Box score component calculations
    goals_component = WEIGHTS['scoring'] * (stats['goals'] ** 0.75)
    assists_component = WEIGHTS['assist'] * (stats['assists'] ** 0.75)
    hockey_assists_component = WEIGHTS['assist'] * 0.5 * (stats['hockey_assists'] ** 0.75)
    turnovers_component = WEIGHTS['turnover'] * ((stats['throwaways'] + stats['drops']) ** 0.75)
    blocks_component = WEIGHTS['defense'] * (stats['blocks'] ** 0.75)
    stalls_component = WEIGHTS['defense'] * (-1) * (stats.get('stalls', 0) ** 0.75)
    callahans_component = 1.0 * (stats.get('callahans', 0) ** 0.75)
    
    box_component = goals_component + assists_component + hockey_assists_component + turnovers_component + blocks_component + stalls_component + callahans_component
    
    # Passing component calculations
    completion_factor = (stats['completion_rate']/100) ** 3.0
    catch_factor = (stats['catch_rate']/100) ** 3.0
    completions_component = (stats['completions'] ** 0.75) * completion_factor
    catches_component = (stats['catches'] ** 0.75) * catch_factor
    passing_component = WEIGHTS['throw'] * (completions_component + catches_component)
    
    # Calculate raw unadjusted PER (without plus-minus component)
    raw_uper = (1 / stats['points_played']) * (box_component + passing_component)
    
    return raw_uper

def calculate_per_from_stats(stats, team_avgs):
    """Calculate PER using pre-loaded stats without additional database queries"""
    if stats['points_played'] == 0:
        return 0
    
    # Define weights
    WEIGHTS = PER_WEIGHTS
    
    # Box score component calculations
    goals_component = WEIGHTS['scoring'] * (stats['goals'] ** 0.75)
    assists_component = WEIGHTS['assist'] * (stats['assists'] ** 0.75)
    hockey_assists_component = WEIGHTS['assist'] * 0.5 * (stats['hockey_assists'] ** 0.75)
    turnovers_component = WEIGHTS['turnover'] * ((stats['throwaways'] + stats['drops']) ** 0.75)
    blocks_component = WEIGHTS['defense'] * (stats['blocks'] ** 0.75)
    stalls_component = WEIGHTS['defense'] * (-1) * (stats.get('stalls', 0) ** 0.75)
    callahans_component = 1.0 * (stats.get('callahans', 0) ** 0.75)
    
    box_component = goals_component + assists_component + hockey_assists_component + turnovers_component + blocks_component + stalls_component + callahans_component
    
    # Passing component calculations
    completion_factor = (stats['completion_rate']/100) ** 3.0
    catch_factor = (stats['catch_rate']/100) ** 3.0
    completions_component = (stats['completions'] ** 0.75) * completion_factor
    catches_component = (stats['catches'] ** 0.75) * catch_factor
    passing_component = WEIGHTS['throw'] * (completions_component + catches_component)
    
    # Get number of points played in each line
    o_line_points = stats.get('o_line_points_played', 0)
    d_line_points = stats.get('d_line_points_played', 0)
    total_points = o_line_points + d_line_points
    
    # Calculate weighted plus-minus component
    plus_minus_component = 0
    if total_points > 0:
        o_line_weight = o_line_points / total_points if o_line_points > 0 else 0
        d_line_weight = d_line_points / total_points if d_line_points > 0 else 0
        
        o_line_component = o_line_weight * (stats.get('o_line_plus_minus_per_point', 0) - team_avgs.get('avg_o_line_plus_minus_per_point', 0))
        d_line_component = d_line_weight * (stats.get('d_line_plus_minus_per_point', 0) - team_avgs.get('avg_d_line_plus_minus_per_point', 0))
        
        plus_minus_component = WEIGHTS['plus_minus'] * (o_line_component + d_line_component)
    
    # Calculate raw unadjusted PER
    raw_uper = (1 / stats['points_played']) * (box_component + passing_component + plus_minus_component)
    
    # Scale to league average of 15
    avg_uper = team_avgs.get('avg_uper', 1)
    if avg_uper <= 0:
        avg_uper = 1
    
    return raw_uper * (15 / avg_uper)

def calculate_impact_score(stats):
    """Calculate impact score for a player"""
    return (stats['goals'] * 2 + stats['assists'] * 1.5 +
            stats['blocks'] * 1.5 - stats['turnovers'])

def calculate_team_avg_stats(player_stats):
    """Calculate team average stats from preloaded player stats"""
    team_avg_stats = {
        'games_played': 0,
        'points_played': 0,
        'o_line_points_played': 0,
        'd_line_points_played': 0,
        'goals': 0,
        'assists': 0,
        'hockey_assists': 0,
        'break_throws': 0,
        'blocks': 0,
        'completions': 0,
        'throwaways': 0,
        'drops': 0,
        'plus_minus': 0,
        'per': 0,
        'completion_rate': 0
    }
    
    # Count players with stats
    player_count = len(player_stats)
    
    if player_count > 0:
        # Sum all stats
        for player_id, stats in player_stats.items():
            team_avg_stats['games_played'] += stats.get('games_played', 0)
            team_avg_stats['points_played'] += stats.get('points_played', 0)
            team_avg_stats['o_line_points_played'] += stats.get('o_line_points_played', 0)
            team_avg_stats['d_line_points_played'] += stats.get('d_line_points_played', 0)
            team_avg_stats['goals'] += stats.get('goals', 0)
            team_avg_stats['assists'] += stats.get('assists', 0)
            team_avg_stats['hockey_assists'] += stats.get('hockey_assists', 0)
            team_avg_stats['break_throws'] += stats.get('break_throws', 0)
            team_avg_stats['blocks'] += stats.get('blocks', 0)
            team_avg_stats['completions'] += stats.get('completions', 0)
            team_avg_stats['throwaways'] += stats.get('throwaways', 0)
            team_avg_stats['drops'] += stats.get('drops', 0)
            team_avg_stats['plus_minus'] += (stats.get('goals', 0) + stats.get('assists', 0) + 
                                           stats.get('blocks', 0) - stats.get('throwaways', 0) - 
                                           stats.get('drops', 0))
            team_avg_stats['per'] += stats.get('per', 0)
        
        # Calculate averages
        for key in team_avg_stats:
            team_avg_stats[key] /= player_count
        
        # Calculate completion rate separately
        total_throws = sum((stats.get('completions', 0) + stats.get('throwaways', 0)) for stats in player_stats.values())
        total_completions = sum(stats.get('completions', 0) for stats in player_stats.values())
        team_avg_stats['completion_rate'] = (total_completions / total_throws * 100) if total_throws > 0 else 0
    
    return team_avg_stats

def calculate_player_line_efficiency(player, is_offensive=True):
    """Calculate a player's line efficiency based on points scored vs points played"""
    # Query for lineups where this player participated
    lineup_query = LineUp.query.join(Point).filter(
        LineUp.player_id == player.id,
        Point.our_line_type == ('O-line' if is_offensive else 'D-line'),
        LineUp.team_organization_id == get_current_team_id(),
        Point.team_organization_id == get_current_team_id()
    )
    
    # Get all points where this player was in the lineup
    lineups = lineup_query.all()
    points_played = len(lineups)
    
    if points_played == 0:
        return 0
    
    # Count points where we scored
    points_scored = sum(1 for lineup in lineups if lineup.point.we_scored)
    
    # Calculate efficiency as scoring percentage
    return points_scored / points_played

def calculate_optimized_line_efficiency(players, player_stats, is_offensive=True):
    """Calculate line efficiency with gender separation using preloaded stats"""
    player_efficiency = {}
    
    for player in players:
        if player.id not in player_stats:
            continue
            
        stats = player_stats[player.id]
        
        # Get the appropriate points played count
        if is_offensive:
            points_played = stats.get('o_line_points_played', 0)
            # We need to calculate how many O-line points with this player resulted in scoring
            # This requires additional data that might not be in the player_stats
        else:
            points_played = stats.get('d_line_points_played', 0)
            # Similar for D-line points
        
        if points_played > 0:
            # We need to query the database to get the actual points data
            # This is a more complex calculation that requires point-level data
            player_efficiency[player] = calculate_player_line_efficiency(player, is_offensive)
    
    return sorted(player_efficiency.items(), key=lambda x: x[1], reverse=True)

# --- Core Statistical Calculation Functions ---
def convert_booleans_for_js(obj):
    """Convert Python booleans to JavaScript-compatible strings"""
    if isinstance(obj, bool):
        return "true" if obj else "false"
    elif isinstance(obj, dict):
        return {k: convert_booleans_for_js(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_booleans_for_js(i) for i in obj]
    return obj

def point_we_scored(point) -> bool:
    """
    Robust 'did we score?' check across schemas.

    Current DB schema (Point model):
      - point.point_outcome == 'scored' / 'conceded'  :contentReference[oaicite:2]{index=2}
    Legacy / alternate schemas may use:
      - point.outcome text ("Goal For Home")
      - point.we_scored boolean/property
    """
    # 1) Current schema
    po = getattr(point, 'point_outcome', None)
    if isinstance(po, str) and po.strip().lower() in ('scored', 'score', 'won'):
        return True
    if isinstance(po, str) and po.strip().lower() in ('conceded', 'concede', 'lost'):
        return False

    # 2) Legacy text outcome
    outcome = getattr(point, 'outcome', None)
    if isinstance(outcome, str) and outcome.strip():
        s = outcome.strip().lower()
        if 'goal for home' in s or 'home scored' in s:
            return True
        if 'goal against home' in s or 'away scored' in s:
            return False

    # 3) Fallback to property/boolean if present
    ws = getattr(point, 'we_scored', None)
    if isinstance(ws, bool):
        return ws

    return False

def get_point_starting_possession(point):
    """
    Returns 'offence' or 'defence' for whether WE start with the disc.

    Priority:
      1) point.starting_possession (what your UI saves)
      2) point.starting_position (legacy)
      3) fallback to our_line_type
    """
    # 1) What input_stats.html saves
    sp = getattr(point, 'starting_possession', None)
    if isinstance(sp, str) and sp.strip().lower() in ('offence', 'offense', 'defence', 'defense'):
        sp = sp.strip().lower()
        return 'offence' if sp in ('offence', 'offense') else 'defence'

    # 2) Legacy field name
    sp = getattr(point, 'starting_position', None)
    if isinstance(sp, str) and sp.strip().lower() in ('offence', 'offense', 'defence', 'defense'):
        sp = sp.strip().lower()
        return 'offence' if sp in ('offence', 'offense') else 'defence'

    # 3) Fallback assumption
    return 'offence' if getattr(point, 'our_line_type', None) == 'O-line' else 'defence'

# Helper function to convert games to a tuple of IDs for caching
def games_to_tuple(games):
    """Convert games to a tuple of IDs for use as cache key"""
    if not games:
        return None
    if isinstance(games, list):
        return tuple(sorted([g.id for g in games]))
    return (games.id,)
