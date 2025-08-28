from app.models.player import Player
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.event import Event, Pull
from sqlalchemy import func
from collections import defaultdict
import math
import logging

logger = logging.getLogger(__name__)

# Original stat_utils.py functions
def calculate_throw_distance(start_x, start_y, end_x, end_y):
    """Calculate throw distance in meters"""
    return ((end_x - start_x)**2 + (end_y - start_y)**2)**0.5

def is_break_throw(throw_position, field_position):
    """Determine if throw is a break throw based on field position"""
    # Implement break throw logic based on field position
    pass

def determine_possession(event_type):
    """Determine possession change based on event type"""
    possession_change_events = [
        'throwaway', 'drop', 'block', 'forced_turnover', 
        'unforced_turnover', 'callahan'
    ]
    return event_type in possession_change_events

def is_point_ending_event(event_type):
    """Check if event ends the point"""
    return event_type in ['goal', 'callahan', 'scored_on']

# Functions from app/utils/__init__.py
def calculate_player_stats(player, games=None):
    """Calculate statistics for a player across all games or specified games."""
    # Base query for events by this player
    query = Event.query.filter_by(player_id=player.id)
    
    # Filter by games if specified
    if games:
        game_ids = [g.id for g in games] if isinstance(games, list) else [games.id]
        points = Point.query.filter(Point.game_id.in_(game_ids)).all()
        point_ids = [p.id for p in points]
        query = query.filter(Event.point_id.in_(point_ids))
    
    # Count different event types
    goals = query.filter_by(event_type='goal').count()
    assists = query.filter_by(event_type='assist').count()
    hockey_assists = query.filter_by(event_type='hockey_assist').count()
    blocks = query.filter_by(event_type='block').count()
    throwaways = query.filter_by(event_type='throwaway').count()
    drops = query.filter_by(event_type='drop').count()
    stalls = query.filter_by(event_type='stall').count()
    callahans = query.filter_by(event_type='callahan').count()
    
    # Count catches and throws
    catches = query.filter_by(event_type='catch').count() + goals  # Goals also count as catches
    throws = query.filter(Event.event_type.in_(['throw', 'assist'])).count()
    completions = throws  # All recorded throws and assists are completions
    
    # Calculate throw distances
    throw_events = query.filter(Event.event_type.in_(['throw', 'assist']), Event.throw_distance != None).all()
    total_throw_distance = sum(e.throw_distance for e in throw_events) if throw_events else 0
    avg_throw_distance = total_throw_distance / len(throw_events) if throw_events else 0
    
    # Calculate completion and catch rates
    completion_rate = completions / (completions + throwaways) * 100 if (completions + throwaways) > 0 else 0
    catch_rate = catches / (catches + drops) * 100 if (catches + drops) > 0 else 0
    
    # Calculate points played
    if games:
        # For specific games
        if isinstance(games, list):
            game_ids = [g.id for g in games]
            points_played = LineUp.query.join(Point).filter(
                LineUp.player_id == player.id,
                Point.game_id.in_(game_ids)
            ).count()
        else:
            # Single game
            points_played = LineUp.query.join(Point).filter(
                LineUp.player_id == player.id,
                Point.game_id == games.id
            ).count()
    else:
        # All games
        points_played = player.points_played
    
    # Calculate o-line and d-line points
    o_line_points = LineUp.query.join(Point).filter(
        LineUp.player_id == player.id,
        Point.our_line_type == 'O-line'
    )
    
    d_line_points = LineUp.query.join(Point).filter(
        LineUp.player_id == player.id,
        Point.our_line_type == 'D-line'
    )
    
    if games:
        if isinstance(games, list):
            game_ids = [g.id for g in games]
            o_line_points = o_line_points.filter(Point.game_id.in_(game_ids))
            d_line_points = d_line_points.filter(Point.game_id.in_(game_ids))
        else:
            o_line_points = o_line_points.filter(Point.game_id == games.id)
            d_line_points = d_line_points.filter(Point.game_id == games.id)
    
    o_line_points_count = o_line_points.count()
    d_line_points_count = d_line_points.count()
    
    # Calculate plus-minus for o-line and d-line
    o_line_plus = 0
    o_line_minus = 0
    d_line_plus = 0
    d_line_minus = 0
    
    for lineup in o_line_points.all():
        point = lineup.point
        if point.we_scored:
            o_line_plus += 1
        else:
            o_line_minus += 1
    
    for lineup in d_line_points.all():
        point = lineup.point
        if point.we_scored:
            d_line_plus += 1
        else:
            d_line_minus += 1
    
    o_line_plus_minus = o_line_plus - o_line_minus
    d_line_plus_minus = d_line_plus - d_line_minus
    
    # Calculate pulls
    pulls = Pull.query.filter_by(player_id=player.id)
    if games:
        if isinstance(games, list):
            game_ids = [g.id for g in games]
            points = Point.query.filter(Point.game_id.in_(game_ids)).all()
            point_ids = [p.id for p in points]
            pulls = pulls.filter(Pull.point_id.in_(point_ids))
        else:
            points = Point.query.filter_by(game_id=games.id).all()
            point_ids = [p.id for p in points]
            pulls = pulls.filter(Pull.point_id.in_(point_ids))
    
    pull_count = pulls.count()
    inbounds_pulls = pulls.filter_by(is_inbounds=True).count()
    
    # Calculate team averages for PER calculation
    all_players = Player.query.filter_by(active=True).all()
    team_avg_o_line_plus_minus_per_point = 0
    team_avg_d_line_plus_minus_per_point = 0
    team_avg_uper = 0
    player_count = 0
    
    for p in all_players:
        p_stats = calculate_basic_stats(p, games)
        if p_stats['o_line_points'] > 0:
            team_avg_o_line_plus_minus_per_point += p_stats['o_line_plus_minus'] / p_stats['o_line_points']
        if p_stats['d_line_points'] > 0:
            team_avg_d_line_plus_minus_per_point += p_stats['d_line_plus_minus'] / p_stats['d_line_points']
        
        # Calculate unadjusted PER for team average
        p_uper = calculate_unadjusted_per(p_stats)
        if p_uper > 0:
            team_avg_uper += p_uper
            player_count += 1
    
    if player_count > 0:
        team_avg_o_line_plus_minus_per_point /= player_count
        team_avg_d_line_plus_minus_per_point /= player_count
        team_avg_uper /= player_count
    
    # Calculate stats dictionary
    stats = {
        'games_played': player.games_played if not games else (len(games) if isinstance(games, list) else 1),
        'points_played': points_played,
        'o_line_points': o_line_points_count,
        'd_line_points': d_line_points_count,
        'goals': goals,
        'assists': assists,
        'hockey_assists': hockey_assists,
        'blocks': blocks,
        'throwaways': throwaways,
        'drops': drops,
        'stalls': stalls,
        'callahans': callahans,
        'catches': catches,
        'throws': throws,
        'completions': completions,
        'total_throw_distance': total_throw_distance,
        'avg_throw_distance': avg_throw_distance,
        'completion_rate': completion_rate,
        'catch_rate': catch_rate,
        'o_line_plus': o_line_plus,
        'o_line_minus': o_line_minus,
        'o_line_plus_minus': o_line_plus_minus,
        'd_line_plus': d_line_plus,
        'd_line_minus': d_line_minus,
        'd_line_plus_minus': d_line_plus_minus,
        'pulls': pull_count,
        'inbounds_pulls': inbounds_pulls,
        'team_avg_o_line_plus_minus_per_point': team_avg_o_line_plus_minus_per_point,
        'team_avg_d_line_plus_minus_per_point': team_avg_d_line_plus_minus_per_point,
        'team_avg_uper': team_avg_uper
    }
    
    # Calculate PER
    stats['unadjusted_per'] = calculate_unadjusted_per(stats)
    stats['per'] = stats['unadjusted_per'] * (15 / team_avg_uper) if team_avg_uper > 0 else 0
    
    return stats

def calculate_basic_stats(player, games=None):
    """Calculate basic statistics for a player (used for team averages)."""
    # Base query for events by this player
    query = Event.query.filter_by(player_id=player.id)
    
    # Filter by games if specified
    if games:
        game_ids = [g.id for g in games] if isinstance(games, list) else [games.id]
        points = Point.query.filter(Point.game_id.in_(game_ids)).all()
        point_ids = [p.id for p in points]
        query = query.filter(Event.point_id.in_(point_ids))
    
    # Count different event types
    goals = query.filter_by(event_type='goal').count()
    assists = query.filter_by(event_type='assist').count()
    blocks = query.filter_by(event_type='block').count()
    throwaways = query.filter_by(event_type='throwaway').count()
    drops = query.filter_by(event_type='drop').count()
    
    # Calculate o-line and d-line points
    o_line_points = LineUp.query.join(Point).filter(
        LineUp.player_id == player.id,
        Point.our_line_type == 'O-line'
    )
    
    d_line_points = LineUp.query.join(Point).filter(
        LineUp.player_id == player.id,
        Point.our_line_type == 'D-line'
    )
    
    if games:
        if isinstance(games, list):
            game_ids = [g.id for g in games]
            o_line_points = o_line_points.filter(Point.game_id.in_(game_ids))
            d_line_points = d_line_points.filter(Point.game_id.in_(game_ids))
        else:
            o_line_points = o_line_points.filter(Point.game_id == games.id)
            d_line_points = d_line_points.filter(Point.game_id == games.id)
    
    o_line_points_count = o_line_points.count()
    d_line_points_count = d_line_points.count()
    
    # Calculate plus-minus for o-line and d-line
    o_line_plus = 0
    o_line_minus = 0
    d_line_plus = 0
    d_line_minus = 0
    
    for lineup in o_line_points.all():
        point = lineup.point
        if point.we_scored:
            o_line_plus += 1
        else:
            o_line_minus += 1
    
    for lineup in d_line_points.all():
        point = lineup.point
        if point.we_scored:
            d_line_plus += 1
        else:
            d_line_minus += 1
    
    o_line_plus_minus = o_line_plus - o_line_minus
    d_line_plus_minus = d_line_plus - d_line_minus
    
    return {
        'goals': goals,
        'assists': assists,
        'blocks': blocks,
        'throwaways': throwaways,
        'drops': drops,
        'o_line_points': o_line_points_count,
        'd_line_points': d_line_points_count,
        'o_line_plus_minus': o_line_plus_minus,
        'd_line_plus_minus': d_line_plus_minus
    }

def calculate_unadjusted_per(stats):
    """Calculate unadjusted Player Efficiency Rating (PER)."""
    points_played = stats['points_played']
    if points_played == 0:
        return 0
    
    # Base formula components
    goals_component = (0.5) * math.pow(stats['goals'], 0.75)
    assists_component = (0.5) * math.pow(stats['assists'], 0.75)
    drops_component = (0.75) * math.pow(stats['drops'], 0.75)
    throwaways_component = (0.75) * math.pow(stats['throwaways'], 0.75)
    blocks_component = (0.75) * math.pow(stats['blocks'], 0.75)
    stalls_component = (0.75) * math.pow(stats['stalls'], 0.75)
    callahans_component = (1.0) * math.pow(stats['callahans'], 0.75)
    
    # Completion and catch percentage components
    completion_component = 0.05 * (math.pow(stats['completions'], 0.75) * math.pow(stats['completion_rate'] / 100, 3.0))
    catch_component = 0.05 * (math.pow(stats['catches'], 0.75) * math.pow(stats['catch_rate'] / 100, 3.0))
    
    # O-line and D-line plus-minus components
    o_line_component = 0
    if stats['o_line_points'] > 0:
        o_line_plus_minus_per_point = stats['o_line_plus_minus'] / stats['o_line_points']
        o_line_component = 0.1 * stats['o_line_points'] * (o_line_plus_minus_per_point - stats['team_avg_o_line_plus_minus_per_point'])
    
    d_line_component = 0
    if stats['d_line_points'] > 0:
        d_line_plus_minus_per_point = stats['d_line_plus_minus'] / stats['d_line_points']
        d_line_component = 0.1 * stats['d_line_points'] * (d_line_plus_minus_per_point - stats['team_avg_d_line_plus_minus_per_point'])
    
    # Pull components
    pull_component = 0
    if points_played > 0:
        pull_component = (stats['pulls'] / points_played) * math.pow(stats['pulls'], 0.25)
    
    inbounds_pull_component = 0
    if stats['pulls'] > 0:
        inbounds_pull_ratio = stats['inbounds_pulls'] / stats['pulls']
        inbounds_pull_component = inbounds_pull_ratio * inbounds_pull_ratio * inbounds_pull_ratio
    
    # Combine all components
    uper = (1 / points_played) * (
        goals_component + assists_component - 
        drops_component - throwaways_component + 
        blocks_component - stalls_component + 
        callahans_component + 
        completion_component + catch_component +
        o_line_component + d_line_component +
        pull_component + inbounds_pull_component
    )
    
    return max(0, uper)  # Ensure PER is not negative

def calculate_team_stats(game):
    """Calculate team statistics for a game."""
    # Basic stats
    o_line_points = len(game.o_line_points)
    o_line_conversions = sum(1 for p in game.o_line_points if p.we_scored)
    o_line_conversion_rate = (o_line_conversions / o_line_points * 100) if o_line_points > 0 else 0
    
    d_line_points = len(game.d_line_points)
    d_line_conversions = sum(1 for p in game.d_line_points if p.we_scored)
    d_line_conversion_rate = (d_line_conversions / d_line_points * 100) if d_line_points > 0 else 0
    
    breaks = sum(1 for p in game.points if p.is_break)
    holds = sum(1 for p in game.points if p.is_hold)
    
    # Event counts
    points = game.points.all()
    point_ids = [p.id for p in points]
    events = Event.query.filter(Event.point_id.in_(point_ids)).all()
    
    goals = sum(1 for e in events if e.event_type == 'goal')
    assists = sum(1 for e in events if e.event_type == 'assist')
    blocks = sum(1 for e in events if e.event_type == 'block')
    throwaways = sum(1 for e in events if e.event_type == 'throwaway')
    drops = sum(1 for e in events if e.event_type == 'drop')
    stalls = sum(1 for e in events if e.event_type == 'stall')
    callahans = sum(1 for e in events if e.event_type == 'callahan')
    
    # Possession stats
    possessions = throwaways + drops + stalls + goals
    turnovers = throwaways + drops + stalls
    turnover_rate = (turnovers / possessions * 100) if possessions > 0 else 0
    
    # Calculate point flow
    point_flow = []
    for point in sorted(points, key=lambda p: p.point_number):
        point_flow.append({
            'point_number': point.point_number,
            'our_score_before': point.our_score_before,
            'their_score_before': point.their_score_before,
            'our_score_after': point.our_score_after,
            'their_score_after': point.their_score_after,
            'our_line_type': point.our_line_type,
            'starting_position': point.starting_position,
            'point_outcome': point.point_outcome,
            'is_break': point.is_break
        })
    
    return {
        'o_line_points': o_line_points,
        'o_line_conversions': o_line_conversions,
        'o_line_conversion_rate': o_line_conversion_rate,
        'd_line_points': d_line_points,
        'd_line_conversions': d_line_conversions,
        'd_line_conversion_rate': d_line_conversion_rate,
        'breaks': breaks,
        'holds': holds,
        'goals': goals,
        'assists': assists,
        'blocks': blocks,
        'throwaways': throwaways,
        'drops': drops,
        'stalls': stalls,
        'callahans': callahans,
        'possessions': possessions,
        'turnovers': turnovers,
        'turnover_rate': turnover_rate,
        'point_flow': point_flow
    }

def calculate_player_game_stats(player, game):
    """Calculate statistics for a player in a specific game."""
    return calculate_player_stats(player, game)

def find_optimal_line(players, line_type, metric='per'):
    """Find the optimal line of 7 players based on the specified metric."""
    if len(players) < 7:
        return players  # Not enough players to form a line
    
    # Filter players by position to ensure a balanced line
    handlers = [p for p in players if p.position == 'handler']
    cutters = [p for p in players if p.position == 'cutter']
    hybrids = [p for p in players if p.position == 'hybrid']
    
    # Calculate stats for each player
    player_stats = {}
    for player in players:
        stats = calculate_player_stats(player)
        player_stats[player.id] = {
            'player': player,
            'stats': stats,
            'metric': stats[metric]
        }
    
    # Sort players by metric
    sorted_handlers = sorted(handlers, key=lambda p: player_stats[p.id]['metric'], reverse=True)
    sorted_cutters = sorted(cutters, key=lambda p: player_stats[p.id]['metric'], reverse=True)
    sorted_hybrids = sorted(hybrids, key=lambda p: player_stats[p.id]['metric'], reverse=True)
    
    # Create a balanced line with at least 2 handlers, 3 cutters, and up to 2 hybrids
    optimal_line = []
    
    # Add handlers (at least 2, up to 3)
    handler_count = min(3, len(sorted_handlers))
    if handler_count < 2 and len(sorted_hybrids) > 0:
        # If not enough handlers, use hybrids
        handler_count = 2
        optimal_line.extend(sorted_handlers)
        hybrid_handlers = sorted_hybrids[:2-len(sorted_handlers)]
        optimal_line.extend(hybrid_handlers)
        sorted_hybrids = sorted_hybrids[2-len(sorted_handlers):]
    else:
        optimal_line.extend(sorted_handlers[:handler_count])
    
    # Add cutters (at least 3, up to 4)
    cutter_count = min(4, len(sorted_cutters))
    if cutter_count < 3 and len(sorted_hybrids) > 0:
        # If not enough cutters, use hybrids
        cutter_count = 3
        optimal_line.extend(sorted_cutters)
        hybrid_cutters = sorted_hybrids[:3-len(sorted_cutters)]
        optimal_line.extend(hybrid_cutters)
        sorted_hybrids = sorted_hybrids[3-len(sorted_cutters):]
    else:
        optimal_line.extend(sorted_cutters[:cutter_count])
    
    # Fill remaining spots with best available players
    remaining_spots = 7 - len(optimal_line)
    if remaining_spots > 0:
        # Combine remaining players and sort by metric
        remaining_players = sorted_handlers[handler_count:] + sorted_cutters[cutter_count:] + sorted_hybrids
        remaining_players.sort(key=lambda p: player_stats[p.id]['metric'], reverse=True)
        optimal_line.extend(remaining_players[:remaining_spots])
    
    return optimal_line

def generate_field_heatmap_data(events, field_width=37, field_length=100, grid_size=5):
    """Generate heatmap data for events on the field."""
    # Create grid
    grid_width = field_width // grid_size + 1
    grid_length = field_length // grid_size + 1
    grid = [[0 for _ in range(grid_length)] for _ in range(grid_width)]
    
    # Count events in each grid cell
    for event in events:
        if event.field_position_x is not None and event.field_position_y is not None:
            x = int(event.field_position_x / grid_size)
            y = int(event.field_position_y / grid_size)
            if 0 <= x < grid_length and 0 <= y < grid_width:
                grid[y][x] += 1
    
    # Convert to format suitable for heatmap visualization
    heatmap_data = []
    for y in range(grid_width):
        for x in range(grid_length):
            if grid[y][x] > 0:
                heatmap_data.append({
                    'x': x * grid_size + grid_size/2,
                    'y': y * grid_size + grid_size/2,
                    'value': grid[y][x]
                })
    
    return heatmap_data

def generate_player_connections(events):
    """Generate data for player connection visualization."""
    connections = defaultdict(int)
    
    # Count throws between players
    for event in events:
        if event.event_type in ['throw', 'assist'] and event.receiver_id:
            connection_key = (event.player_id, event.receiver_id)
            connections[connection_key] += 1
    
    # Convert to format suitable for network visualization
    nodes = set()
    links = []
    
    for (thrower_id, receiver_id), count in connections.items():
        nodes.add(thrower_id)
        nodes.add(receiver_id)
        links.append({
            'source': thrower_id,
            'target': receiver_id,
            'value': count
        })
    
    # Get player details for nodes
    node_data = []
    for player_id in nodes:
        player = Player.query.get(player_id)
        if player:
            node_data.append({
                'id': player.id,
                'name': player.name,
                'position': player.position,
                'jersey_number': player.jersey_number
            })
    
    return {
        'nodes': node_data,
        'links': links
    }

def calculate_unadjusted_per(stats):
    """Calculate unadjusted Player Efficiency Rating (PER)."""
    points_played = stats['points_played']
    if points_played == 0:
        return 0
    
    # Base formula components
    goals_component = (0.5) * math.pow(stats['goals'], 0.75)
    assists_component = (0.5) * math.pow(stats['assists'], 0.75)
    drops_component = (0.75) * math.pow(stats['drops'], 0.75)
    throwaways_component = (0.75) * math.pow(stats['throwaways'], 0.75)
    blocks_component = (0.75) * math.pow(stats['blocks'], 0.75)
    stalls_component = (0.75) * math.pow(stats['stalls'], 0.75)
    callahans_component = (1.0) * math.pow(stats['callahans'], 0.75)
    
    # Completion and catch percentage components
    completion_component = 0.05 * (math.pow(stats['completions'], 0.75) * math.pow(stats['completion_rate'] / 100, 3.0))
    catch_component = 0.05 * (math.pow(stats['catches'], 0.75) * math.pow(stats['catch_rate'] / 100, 3.0))
    
    # O-line and D-line plus-minus components
    o_line_component = 0
    if stats['o_line_points'] > 0:
        o_line_plus_minus_per_point = stats['o_line_plus_minus'] / stats['o_line_points']
        o_line_component = 0.1 * stats['o_line_points'] * (o_line_plus_minus_per_point - stats['team_avg_o_line_plus_minus_per_point'])
    
    d_line_component = 0
    if stats['d_line_points'] > 0:
        d_line_plus_minus_per_point = stats['d_line_plus_minus'] / stats['d_line_points']
        d_line_component = 0.1 * stats['d_line_points'] * (d_line_plus_minus_per_point - stats['team_avg_d_line_plus_minus_per_point'])
    
    # Pull components
    pull_component = 0
    if points_played > 0:
        pull_component = (stats['pulls'] / points_played) * math.pow(stats['pulls'], 0.25)
    
    inbounds_pull_component = 0
    if stats['pulls'] > 0:
        inbounds_pull_ratio = stats['inbounds_pulls'] / stats['pulls']
        inbounds_pull_component = inbounds_pull_ratio * inbounds_pull_ratio * inbounds_pull_ratio
    
    # Combine all components
    uper = (1 / points_played) * (
        goals_component + assists_component - 
        drops_component - throwaways_component + 
        blocks_component - stalls_component + 
        callahans_component + 
        completion_component + catch_component +
        o_line_component + d_line_component +
        pull_component + inbounds_pull_component
    )
    
    return max(0, uper)  # Ensure PER is not negative



def generate_field_heatmap_data(events, field_width=37, field_length=100, grid_size=5):
    """Generate heatmap data for events on the field."""
    # Create grid
    grid_width = field_width // grid_size + 1
    grid_length = field_length // grid_size + 1
    grid = [[0 for _ in range(grid_length)] for _ in range(grid_width)]
    
    # Count events in each grid cell
    for event in events:
        if event.field_position_x is not None and event.field_position_y is not None:
            x = int(event.field_position_x / grid_size)
            y = int(event.field_position_y / grid_size)
            if 0 <= x < grid_length and 0 <= y < grid_width:
                grid[y][x] += 1
    
    # Convert to format suitable for heatmap visualization
    heatmap_data = []
    for y in range(grid_width):
        for x in range(grid_length):
            if grid[y][x] > 0:
                heatmap_data.append({
                    'x': x * grid_size + grid_size/2,
                    'y': y * grid_size + grid_size/2,
                    'value': grid[y][x]
                })
    
    return heatmap_data