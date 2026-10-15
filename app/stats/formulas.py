"""Pure stat formulas: no database access."""



PER_WEIGHTS = {
    'scoring': 0.5,
    'assist': 0.5,
    'turnover': -0.75,
    'defense': 0.75,
    'throw': 0.05,
    'plus_minus': 0.1
}

TURNOVER_EVENTS = {'throwaway', 'drop', 'stall'}

def _box_and_passing(stats):
    """The event-count part of PER: box score (goals, assists, blocks,
    turnovers...) plus passing volume weighted by completion/catch rate."""
    w = PER_WEIGHTS
    box = (w['scoring'] * stats['goals'] ** 0.75
           + w['assist'] * stats['assists'] ** 0.75
           + w['assist'] * 0.5 * stats['hockey_assists'] ** 0.75
           + w['turnover'] * (stats['throwaways'] + stats['drops']) ** 0.75
           + w['defense'] * stats['blocks'] ** 0.75
           - w['defense'] * stats.get('stalls', 0) ** 0.75
           + 1.0 * stats.get('callahans', 0) ** 0.75)
    completion_factor = (stats['completion_rate'] / 100) ** 3.0
    catch_factor = (stats['catch_rate'] / 100) ** 3.0
    passing = w['throw'] * (stats['completions'] ** 0.75 * completion_factor
                            + stats['catches'] ** 0.75 * catch_factor)
    return box + passing


def calculate_unadjusted_per(stats):
    """Raw PER per point, without the plus-minus term or league scaling.
    Used to work out the team average that PER is scaled against."""
    if stats['points_played'] == 0:
        return 0
    return (1 / stats['points_played']) * _box_and_passing(stats)

def calculate_per(stats, team_avgs):
    """Player Efficiency Rating, scaled so the team average is 15.

    PER = (box score + passing + plus-minus vs team average) per point,
    multiplied by 15 / team average unadjusted PER. team_avgs comes from
    app.stats.team.calculate_team_averages for the same set of games."""
    if stats['points_played'] == 0:
        return 0

    o_line_points = stats.get('o_line_points_played', 0)
    d_line_points = stats.get('d_line_points_played', 0)
    total_points = o_line_points + d_line_points
    plus_minus = 0
    if total_points > 0:
        o_part = (o_line_points / total_points) * (
            stats.get('o_line_plus_minus_per_point', 0) - team_avgs.get('avg_o_line_plus_minus_per_point', 0))
        d_part = (d_line_points / total_points) * (
            stats.get('d_line_plus_minus_per_point', 0) - team_avgs.get('avg_d_line_plus_minus_per_point', 0))
        plus_minus = PER_WEIGHTS['plus_minus'] * (o_part + d_part)

    raw = (1 / stats['points_played']) * (_box_and_passing(stats) + plus_minus)
    avg_uper = team_avgs.get('avg_uper', 1)
    if avg_uper <= 0:
        avg_uper = 1
    return raw * (15 / avg_uper)

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


def calculate_optimized_line_efficiency(players, player_stats, is_offensive=True):
    """Players ranked by line conversion (share of their O-line points we
    held, or D-line points we broke), for the games player_stats covers.
    Returns [(player, fraction 0-1), ...], best first."""
    line = 'o_line' if is_offensive else 'd_line'
    player_efficiency = {}
    for player in players:
        stats = player_stats.get(player.id)
        if stats and stats.get(f'{line}_points_played', 0) > 0:
            player_efficiency[player] = (stats[f'{line}_points_scored']
                                         / stats[f'{line}_points_played'])
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
