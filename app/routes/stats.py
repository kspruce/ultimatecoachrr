from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.point import Point, LineUp
from app.models.event import Event
from app.models.stats import PlayerPointStats#
from app.models.throws import Throw
from app.models.clip import Clip
import json
import math
from app.utils.utils import admin_required
from datetime import datetime

bp = Blueprint('stats_dashboard', __name__, url_prefix='/stats')

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

def calculate_hockey_assists(player, games=None):
    """Calculate hockey assists (second-to-last pass before a goal)"""
    # Start with base query for all throws in points
    query = Throw.query.filter_by(thrower_id=player.id)
    
    if games:
        if isinstance(games, list):
            point_ids = [p.id for g in games for p in g.points]
        else:
            point_ids = [p.id for p in games.points]
        query = query.filter(Throw.point_id.in_(point_ids))
    
    hockey_assists = 0
    
    # Get all throws by this player
    player_throws = query.all()
    
    for throw in player_throws:
        # For each throw, check if the receiver made an assist
        if throw.receiver_id:
            # Find if the receiver made an assist in the same point after this throw
            assist = Throw.query.filter(
                Throw.thrower_id == throw.receiver_id,
                Throw.point_id == throw.point_id,
                Throw.throw_type == 'assist',
                Throw.created_at > throw.created_at
            ).order_by(Throw.created_at).first()
            
            if assist:
                hockey_assists += 1
    
    return hockey_assists


def get_player_throw_stats(player, games=None):
    """Get comprehensive throwing statistics for a player"""
    query = Throw.query.filter(
        (Throw.thrower_id == player.id) |
        (Throw.receiver_id == player.id)
    )
    
    if games:
        if isinstance(games, list):
            point_ids = [p.id for g in games for p in g.points]
        else:
            point_ids = [p.id for p in games.points]
        query = query.filter(Throw.point_id.in_(point_ids))
    
    throws = query.all()
    
    stats = {
        'throws_made': len([t for t in throws if t.thrower_id == player.id]),
        'throws_received': len([t for t in throws if t.receiver_id == player.id]),
        'assists': len([t for t in throws if t.thrower_id == player.id and t.throw_type == 'assist']),
        'hockey_assists': len([t for t in throws if t.thrower_id == player.id and t.throw_type == 'hockey_assist']),
        'throw_vectors': [
            {
                'start_x': t.x_start,  
                'start_y': t.y_start,  
                'end_x': t.x_end,      
                'end_y': t.y_end,      
                'type': t.throw_type
            }
            for t in throws if t.thrower_id == player.id
        ],
        'total_throw_distance': sum(t.distance for t in throws if t.thrower_id == player.id),
        'avg_throw_distance': 0
    }
    
    if stats['throws_made'] > 0:
        stats['avg_throw_distance'] = stats['total_throw_distance'] / stats['throws_made']
    

    # Add throw direction categorization with 16 directions
    throw_directions = {
        'E': 0, 'ENE': 0, 'NE': 0, 'NNE': 0, 
        'N': 0, 'NNW': 0, 'NW': 0, 'WNW': 0, 
        'W': 0, 'WSW': 0, 'SW': 0, 'SSW': 0, 
        'S': 0, 'SSE': 0, 'SE': 0, 'ESE': 0
    }
    
    completion_by_direction = {
        'E': 0, 'ENE': 0, 'NE': 0, 'NNE': 0, 
        'N': 0, 'NNW': 0, 'NW': 0, 'WNW': 0, 
        'W': 0, 'WSW': 0, 'SW': 0, 'SSW': 0, 
        'S': 0, 'SSE': 0, 'SE': 0, 'ESE': 0
    }
    
    for throw in throws:
        if throw.thrower_id == player.id and throw.x_start is not None and throw.y_start is not None and throw.x_end is not None and throw.y_end is not None:
            # Calculate angle
            dx = throw.x_end - throw.x_start
            dy = throw.y_end - throw.y_start
            angle = math.atan2(dy, dx)
            
            # Convert to degrees and normalize to 0-360
            degrees = (angle * 180 / math.pi)
            if degrees < 0:
                degrees += 360
                
            # Map angle to 16-point direction (each direction covers 22.5 degrees)
            if degrees >= 348.75 or degrees < 11.25:
                direction = 'E'  # Right/East (0°) = Forward
            elif degrees >= 11.25 and degrees < 33.75:
                direction = 'ENE'
            elif degrees >= 33.75 and degrees < 56.25:
                direction = 'NE'
            elif degrees >= 56.25 and degrees < 78.75:
                direction = 'NNE'
            elif degrees >= 78.75 and degrees < 101.25:
                direction = 'N'  # Up/North (90°) = Right
            elif degrees >= 101.25 and degrees < 123.75:
                direction = 'NNW'
            elif degrees >= 123.75 and degrees < 146.25:
                direction = 'NW'
            elif degrees >= 146.25 and degrees < 168.75:
                direction = 'WNW'
            elif degrees >= 168.75 and degrees < 191.25:
                direction = 'W'  # Left/West (180°) = Back
            elif degrees >= 191.25 and degrees < 213.75:
                direction = 'WSW'
            elif degrees >= 213.75 and degrees < 236.25:
                direction = 'SW'
            elif degrees >= 236.25 and degrees < 258.75:
                direction = 'SSW'
            elif degrees >= 258.75 and degrees < 281.25:
                direction = 'S'  # Down/South (270°) = Left
            elif degrees >= 281.25 and degrees < 303.75:
                direction = 'SSE'
            elif degrees >= 303.75 and degrees < 326.25:
                direction = 'SE'
            else:
                direction = 'ESE'
                    
            throw_directions[direction] += 1
            
            # If it's a completion, also increment completion count
            if throw.is_completion:
                completion_by_direction[direction] += 1


    
    stats['throw_directions'] = throw_directions    
    stats['completion_by_direction'] = completion_by_direction
    
    return stats

def calculate_team_radar_stats(games, team_name):
    """Calculate team average statistics for radar charts"""
    # Get all active players from the team
    players = Player.query.filter_by(active=True, team=team_name).all()
    
    if not players or not games:
        return default_team_stats()
    
    # Initialize counters
    total_stats = {
        # Offensive stats
        'throws': 0,
        'completions': 0,
        'completion_rate_sum': 0,
        'assists': 0,
        'hockey_assists': 0,
        'goals': 0,
        'catches': 0,
        'catch_rate_sum': 0,
        'avg_throw_distance_sum': 0,
        'hucks': 0,
        'o_line_points_played': 0,
        
        # Defensive stats
        'blocks': 0,
        'stalls': 0,
        'shutdowns': 0,
        'd_line_plus_minus': 0,
        'd_line_points_played': 0,
        
        # Player counters
        'players_with_stats': 0,
        'players_with_o_line_points': 0,
        'players_with_d_line_points': 0
    }
    
    # Aggregate stats from all players
    for player in players:
        player_stats = get_player_base_stats(player, games)
        
        if player_stats['points_played'] > 0:
            total_stats['players_with_stats'] += 1
            
            # Offensive stats
            total_stats['throws'] += player_stats['throws']
            total_stats['completions'] += player_stats['completions']
            if player_stats['completion_rate'] > 0:
                total_stats['completion_rate_sum'] += player_stats['completion_rate']
            total_stats['assists'] += player_stats['assists']
            total_stats['hockey_assists'] += player_stats['hockey_assists']
            total_stats['goals'] += player_stats['goals']
            total_stats['catches'] += player_stats['catches']
            if player_stats['catch_rate'] > 0:
                total_stats['catch_rate_sum'] += player_stats['catch_rate']
            if player_stats['avg_throw_distance'] > 0:
                total_stats['avg_throw_distance_sum'] += player_stats['avg_throw_distance']
            
            # Add hucks
            total_stats['hucks'] += calculate_hucks(player, games)
            
            # O-line stats
            if player_stats['o_line_points_played'] > 0:
                total_stats['o_line_points_played'] += player_stats['o_line_points_played']
                total_stats['players_with_o_line_points'] += 1
            
            # D-line stats
            if player_stats['d_line_points_played'] > 0:
                total_stats['blocks'] += player_stats['blocks']
                total_stats['stalls'] += player_stats.get('stalls', 0)
                total_stats['shutdowns'] += player_stats.get('shutdowns', 0)
                total_stats['d_line_plus_minus'] += player_stats['d_line_plus_minus']
                total_stats['d_line_points_played'] += player_stats['d_line_points_played']
                total_stats['players_with_d_line_points'] += 1
    
    # Calculate averages
    team_avgs = {}
    
    # Avoid division by zero
    players_with_stats = max(1, total_stats['players_with_stats'])
    o_line_points = max(1, total_stats['o_line_points_played'])
    d_line_points = max(1, total_stats['d_line_points_played'])
    
    # Offensive averages
    team_avgs['completion_rate'] = total_stats['completion_rate_sum'] / players_with_stats
    team_avgs['catch_rate'] = total_stats['catch_rate_sum'] / players_with_stats
    team_avgs['avg_throw_distance'] = total_stats['avg_throw_distance_sum'] / players_with_stats
    
    # Per-point averages
    team_avgs['assists_per_point'] = total_stats['assists'] / o_line_points
    team_avgs['hockey_assists_per_point'] = total_stats['hockey_assists'] / o_line_points
    team_avgs['goals_per_point'] = total_stats['goals'] / o_line_points
    team_avgs['throws_per_point'] = total_stats['throws'] / o_line_points
    team_avgs['catches_per_point'] = total_stats['catches'] / o_line_points
    team_avgs['hucks_per_point'] = total_stats['hucks'] / o_line_points
    
    # Defensive averages
    team_avgs['blocks_per_point'] = total_stats['blocks'] / d_line_points
    team_avgs['stalls_per_point'] = total_stats['stalls'] / d_line_points
    team_avgs['shutdowns_per_point'] = total_stats['shutdowns'] / d_line_points
    team_avgs['d_line_plus_minus_per_point'] = total_stats['d_line_plus_minus'] / d_line_points
    team_avgs['turnovers_forced_per_point'] = (total_stats['blocks'] + total_stats['stalls']) / d_line_points
    
    return team_avgs

def default_team_stats():
    """Return default team stats when no data is available"""
    return {
        'completion_rate': 0,
        'catch_rate': 0,
        'avg_throw_distance': 0,
        'assists_per_point': 0,
        'hockey_assists_per_point': 0,
        'goals_per_point': 0,
        'throws_per_point': 0,
        'catches_per_point': 0,
        'hucks_per_point': 0,
        'blocks_per_point': 0,
        'stalls_per_point': 0,
        'shutdowns_per_point': 0,
        'd_line_plus_minus_per_point': 0,
        'turnovers_forced_per_point': 0
    }


def calculate_per(player, games=None, team_avgs=None):
    """
    Standardized PER calculation without expensive max normalization
    """
    stats = get_player_base_stats(player, games)
    
    if stats['points_played'] == 0:
        return 0
    
    # If team_avgs is not provided, calculate it
    if team_avgs is None:
        team_avgs = calculate_team_averages(games)
        
    # Define weights
    WEIGHTS = {
        'scoring': 0.5,
        'assist': 0.5,
        'turnover': -0.75,
        'defense': 0.75,
        'throw': 0.05,
        'plus_minus': 0.1
    }

    # Calculate raw PER
    uper = (1 / stats['points_played']) * (
        (WEIGHTS['scoring'] * (stats['goals'] ** 0.75)) +
        (WEIGHTS['assist'] * (stats['assists'] ** 0.75)) +
        (WEIGHTS['assist'] * 0.5 * (stats['hockey_assists'] ** 0.75)) +
        (WEIGHTS['turnover'] * ((stats['throwaways'] + stats['drops']) ** 0.75)) +
        (WEIGHTS['defense'] * (stats['blocks'] ** 0.75)) +
        (WEIGHTS['throw'] * (
            (stats['completions'] ** 0.75) * ((stats['completion_rate']/100) ** 3.0) +
            (stats['catches'] ** 0.75) * ((stats['catch_rate']/100) ** 3.0)
        )) +
        (WEIGHTS['plus_minus'] * (
            stats.get('o_line_plus_minus_per_point', 0) - team_avgs.get('avg_o_line_plus_minus_per_point', 0) +
            stats.get('d_line_plus_minus_per_point', 0) - team_avgs.get('avg_d_line_plus_minus_per_point', 0)
        ))
    )

    # Normalize to league average
    avg_uper = team_avgs.get('avg_uper', 1)
    if avg_uper <= 0:
        avg_uper = 1
    
    # Return the scaled PER directly
    return uper * (15 / avg_uper)



def get_player_base_stats(player, games=None):
    """Get comprehensive player statistics"""
    print(f"Calculating stats for player {player.id}")
    # Start with default values for ALL possible stats
    stats = {
        # Basic stats
        'points_played': 0,
        'games_played': 0,
        'goals': 0,
        'assists': 0,
        'hockey_assists': 0,
        'blocks': 0,
        'catches': 0,
        'throws': 0,
        'completions': 0,
        'throwaways': 0,
        'drops': 0,
        'turnovers': 0,
        
        # Calculated rates
        'completion_rate': 0,
        'catch_rate': 0,
        
        # O/D line stats
        'o_line_points_played': 0,
        'd_line_points_played': 0,
        'o_line_plus_minus': 0,
        'd_line_plus_minus': 0,
        'o_line_plus_minus_per_point': 0,
        'd_line_plus_minus_per_point': 0,
        
        # Throw statistics
        'total_throw_distance': 0,
        'avg_throw_distance': 0,
        'throw_vectors': [], #store throw vectors
        'break_throws': 0,
        'break_throw_percentage': 0,
        
        # Efficiency metrics
        'per': 0,
        'plus_minus': 0,
        
        # Additional stats
        'callahans': 0,
        'stalls': 0,
        'offensive_points_played': 0,
        'defensive_points_played': 0,
        'offensive_conversion_rate': 0,
        'defensive_conversion_rate': 0,
        
        # Clip statistics
        'clips': 0,
        'highlight_plays': 0
    }
    
    try:
        # Get points played
        lineup_query = LineUp.query.filter_by(player_id=player.id)
        if games:
            if isinstance(games, list):
                point_ids = [p.id for g in games for p in g.points]
            else:
                point_ids = [p.id for p in games.points]
            lineup_query = lineup_query.filter(LineUp.point_id.in_(point_ids))
        
        points_played = lineup_query.all()
        stats['points_played'] = len(points_played)
        
        if stats['points_played'] == 0:
            return stats

        # Get games played
        if games:
            stats['games_played'] = len(games) if isinstance(games, list) else 1
        else:
            stats['games_played'] = len(set(lineup.point.game_id for lineup in points_played))

        # Get all throws for this player
        throws_query = Throw.query.filter(Throw.thrower_id == player.id)
        if games:
            throws_query = throws_query.filter(Throw.point_id.in_(point_ids))

        # Get unique throws by coordinates and timestamp
        unique_throws = {}
        for throw in throws_query.all():
            # Create a key based on coordinates
            key = (throw.x_start, throw.y_start, throw.x_end, throw.y_end)
            if key not in unique_throws:
                unique_throws[key] = throw

        # Count different types of throws
        stats['throws'] = len(unique_throws)
        stats['completions'] = sum(1 for t in unique_throws.values() if t.is_completion)
        stats['assists'] = sum(1 for t in unique_throws.values() if t.throw_type == 'assist')
        stats['hockey_assists'] = sum(1 for t in unique_throws.values() if t.throw_type == 'hockey_assist')
        stats['throwaways'] = sum(1 for t in unique_throws.values() if t.throw_type == 'throwaway')

        # Calculate throw distances
        total_distance = sum(t.calculate_distance() for t in unique_throws.values() if t.calculate_distance())
        stats['total_throw_distance'] = total_distance
        stats['avg_throw_distance'] = total_distance / stats['throws'] if stats['throws'] > 0 else 0

        # Store throw vectors for visualization
        stats['throw_vectors'] = [
            {
                'start_x': t.x_start,
                'start_y': t.y_start,
                'end_x': t.x_end,
                'end_y': t.y_end,
                'type': t.throw_type,
                'distance': t.calculate_distance()
            }
            for t in unique_throws.values()
        ]

        # Get all events for this player
        events_query = Event.query.filter_by(player_id=player.id)
        if games:
            events_query = events_query.filter(Event.point_id.in_(point_ids))
        
        # Count each event type
        for event in events_query.all():
            if event.event_type == 'goal':
                stats['goals'] += 1
            elif event.event_type == 'block':
                stats['blocks'] += 1
            elif event.event_type == 'catch':
                stats['catches'] += 1
            elif event.event_type == 'drop':
                stats['drops'] += 1

        # Calculate derived stats
        stats['turnovers'] = stats['throwaways'] + stats['drops']
        
        # Calculate rates
        if stats['throws'] > 0:
            stats['completion_rate'] = (stats['completions'] / stats['throws']) * 100
        if stats['catches'] + stats['drops'] > 0:
            stats['catch_rate'] = (stats['catches'] / (stats['catches'] + stats['drops'])) * 100

        # Calculate plus/minus
        stats['plus_minus'] = (
            stats['goals'] + 
            stats['assists'] + 
            stats['blocks'] - 
            stats['turnovers']
        )

        print(f"Stats retrieved for {player.name}:")
        print(f"Throws: {stats['throws']}")
        print(f"Total Distance: {stats['total_throw_distance']:.1f}m")
        print(f"Avg Distance: {stats['avg_throw_distance']:.1f}m")
        print(f"Goals: {stats['goals']}")
        print(f"Assists: {stats['assists']}")
        print(f"Blocks: {stats['blocks']}")
        print(f"Turnovers: {stats['turnovers']}")
        print(f"Plus/Minus: {stats['plus_minus']}")

        # Calculate O-line and D-line stats
        o_line_points = [p for p in points_played if p.point.our_line_type == 'O-line']
        d_line_points = [p for p in points_played if p.point.our_line_type == 'D-line']

        stats['o_line_points_played'] = len(o_line_points)
        stats['d_line_points_played'] = len(d_line_points)

        # Calculate plus/minus for each line
        for point in o_line_points:
            if point.point.we_scored:
                stats['o_line_plus_minus'] += 1
            if point.point.they_scored:
                stats['o_line_plus_minus'] -= 1

        for point in d_line_points:
            if point.point.we_scored:
                stats['d_line_plus_minus'] += 1
            if point.point.they_scored:
                stats['d_line_plus_minus'] -= 1

        # Calculate per point stats
        if stats['o_line_points_played'] > 0:
            stats['o_line_plus_minus_per_point'] = stats['o_line_plus_minus'] / stats['o_line_points_played']
        if stats['d_line_points_played'] > 0:
            stats['d_line_plus_minus_per_point'] = stats['d_line_plus_minus'] / stats['d_line_points_played']

        # Get clips statistics using new relationship pattern
        clips_query = player.clip_appearances
        if games:
            if isinstance(games, list):
                game_ids = [g.id for g in games]
                clips_query = clips_query.filter(Clip.game_id.in_(game_ids))
            else:
                clips_query = clips_query.filter(Clip.game_id == games.id)
        
        stats['clips'] = clips_query.count()
        # You could add more clip-related statistics here if needed
        
        # Count break throws
        stats['break_throws'] = sum(1 for t in unique_throws.values() if t.break_throw)
        
        # Count hockey assists directly from throw type
        stats['hockey_assists'] = sum(1 for t in unique_throws.values() if t.throw_type == 'hockey_assist')

        

    except Exception as e:
        print(f"Error getting stats for {player.name}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return stats






def process_heatmap_data(team_name=None, player_id=None, opposition_team=None):
    """Process throw data for heatmap visualization"""
    query = Throw.query
    
    if player_id:
        query = query.filter(Throw.thrower_id == player_id)
    if opposition_team:
        query = query.filter(Throw.opposition_team == opposition_team)
    if team_name:
        query = query.join(Throw.thrower).filter(Player.team == team_name)
    
    throws = query.all()
    heatmap_data = []
    
    # Add throw start positions
    for throw in throws:
        if throw.x_start is not None and throw.y_start is not None:
            heatmap_data.append({
                'x': throw.x_start,
                'y': throw.y_start,
                'value': 1,
                'type': 'throw_start'
            })
    
    # For throwaways, still use Events model
    throwaway_query = Event.query.filter_by(event_type='throwaway')
    if player_id:
        throwaway_query = throwaway_query.filter_by(player_id=player_id)
    if team_name:
        throwaway_query = throwaway_query.join(Event.player).filter(Player.team == team_name)
    
    for event in throwaway_query.all():
        if event.field_position_x is not None and event.field_position_y is not None:
            heatmap_data.append({
                'x': event.field_position_x,
                'y': event.field_position_y,
                'value': 1,
                'type': 'throwaway'
            })
    
    return heatmap_data

def generate_player_connections(team_name=None, opposition_team=None):
    """Generate player connection data using Throws model"""
    query = Throw.query.filter(Throw.receiver_id.isnot(None))
    
    if team_name:
        query = query.join(Throw.thrower).filter(Player.team == team_name)
    if opposition_team:
        query = query.filter(Throw.opposition_team == opposition_team)
    
    throws = query.all()
    
    # Track unique players and their connections
    players = set()
    connections = {}
    
    for throw in throws:
        players.add(throw.thrower_id)
        players.add(throw.receiver_id)
        
        key = f"{throw.thrower_id}-{throw.receiver_id}"
        if key in connections:
            connections[key]['value'] += 1
        else:
            connections[key] = {
                'source': throw.thrower_id,
                'target': throw.receiver_id,
                'value': 1
            }
    
    # Create nodes list
    nodes = []
    for player_id in players:
        player = Player.query.get(player_id)
        if player:
            nodes.append({
                'id': player.id,
                'name': player.name,
                'jersey_number': player.jersey_number,
                'position': player.position
            })
    
    return {
        'nodes': nodes,
        'links': list(connections.values())
    }



# --- Additional Helper Functions ---

def calculate_team_averages(games=None):
    """
    Calculate team averages for PER normalization
    """
    players = Player.query.filter_by(active=True).all()
    
    totals = {
        'o_line_plus_minus': 0,
        'o_line_points': 0,
        'd_line_plus_minus': 0,
        'd_line_points': 0,
        'uper_total': 0,
        'player_count': 0
    }

    for player in players:
        stats = get_player_base_stats(player, games)
        if stats['points_played'] > 0:
            totals['player_count'] += 1
            totals['o_line_plus_minus'] += stats.get('o_line_plus_minus', 0)
            totals['o_line_points'] += stats.get('o_line_points_played', 0)
            totals['d_line_plus_minus'] += stats.get('d_line_plus_minus', 0)
            totals['d_line_points'] += stats.get('d_line_points_played', 0)
            totals['uper_total'] += calculate_unadjusted_per(stats)

    return {
        'avg_o_line_plus_minus_per_point': (totals['o_line_plus_minus'] / totals['o_line_points']) if totals['o_line_points'] > 0 else 0,
        'avg_d_line_plus_minus_per_point': (totals['d_line_plus_minus'] / totals['d_line_points']) if totals['d_line_points'] > 0 else 0,
        'avg_uper': totals['uper_total'] / totals['player_count'] if totals['player_count'] > 0 else 1
    }


def calculate_game_stats(game):
    """
    Calculate comprehensive game statistics
    """
    stats = {
        'o_line_points': len(game.o_line_points),
        'o_line_conversions': sum(1 for p in game.o_line_points if p.we_scored),
        'd_line_points': len(game.d_line_points),
        'd_line_conversions': sum(1 for p in game.d_line_points if p.we_scored),
        'breaks': sum(1 for p in game.points if p.is_break),
        'holds': sum(1 for p in game.points if p.is_hold),
        'turnovers': 0,
        'possessions': 0,
        'point_flow': []
    }
    
    # Calculate conversion rates
    stats['o_line_conversion_rate'] = (stats['o_line_conversions'] / stats['o_line_points'] * 100) if stats['o_line_points'] > 0 else 0
    stats['d_line_conversion_rate'] = (stats['d_line_conversions'] / stats['d_line_points'] * 100) if stats['d_line_points'] > 0 else 0
    
    # Calculate point flow data
    for point in sorted(game.points, key=lambda p: p.point_number):
        stats['point_flow'].append({
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
        
        # Count turnovers and possessions
        point_events = Event.query.filter_by(point_id=point.id).order_by(Event.timestamp).all()
        stats['turnovers'] += sum(1 for e in point_events if e.event_type in ['throwaway', 'drop', 'stall'])
        stats['possessions'] += count_possessions(point_events)
    
    return stats

# --- Routes ---

@bp.route('/debug/throws')
@login_required
def debug_throws():
    """Debug view for throws model"""
    throws = Throw.query.order_by(Throw.created_at.desc()).limit(100).all()
    return render_template('stats/debug_throws.html', throws=throws)

@bp.route('/')
@login_required
def index():
    # Default values for all required variables
    default_context = {
        'team_summary': {
            'wins': 0,
            'losses': 0,
            'ties': 0,
            'total_points': 0,
            'o_line_points': 0,
            'o_line_conversions': 0,
            'd_line_points': 0,
            'd_line_conversions': 0,
            'breaks': 0,
            'win_percentage': 0,
            'o_line_conversion_rate': 0,
            'd_line_conversion_rate': 0
        },
        'players': [],
        'recent_games': [],
        'team_stats': [],
        'player_stats': {},
        'o_line_players': [],
        'd_line_players': [],
        'heatmap_data': [],
        'connection_data': {'nodes': [], 'links': []}
    }

    try:
        # Get team name from current user's player
        team_name = None
        if hasattr(current_user, 'player') and current_user.player:
            team_name = current_user.player.team

        # Get active players
        players = Player.query.filter_by(active=True)
        if team_name:
            players = players.filter_by(team=team_name)
        players = players.all()
        
        if not players:
            flash("No active players found", "warning")
            return render_template('stats/index.html', **default_context)

        # Calculate team summary and stats
        recent_games = Game.query.order_by(Game.date.desc()).limit(5).all()
        if recent_games:
            team_summary = calculate_team_summary(recent_games)
            team_stats = []
            for game in recent_games:
                try:
                    stats = calculate_game_stats(game)
                    team_stats.append({'stats': stats})
                except Exception as e:
                    print(f"Error calculating stats for game {game.id}: {str(e)}")
                    continue
        else:
            team_summary = default_context['team_summary']
            team_stats = []

        # Calculate team averages once for all players
        team_avgs = calculate_team_averages(recent_games)
        
        # Calculate player stats
        player_stats = {}
        for player in players:
            try:
                stats = get_player_base_stats(player)
                if stats['points_played'] > 0:
                    # Pass the team_avgs to calculate_per
                    stats['per'] = calculate_per(player, team_avgs=team_avgs)
                    player_stats[player.id] = stats
            except Exception as e:
                print(f"Error calculating stats for player {player.id}: {str(e)}")
                continue

        # Determine O-line and D-line players based on point participation
        o_line_candidates = []
        d_line_candidates = []

        for player in players:
            # Get all points where player was in lineup
            lineup_query = LineUp.query.join(Point).filter(LineUp.player_id == player.id)
            
            # Count O-line and D-line points
            o_line_points = lineup_query.filter(Point.our_line_type == 'O-line').count()
            d_line_points = lineup_query.filter(Point.our_line_type == 'D-line').count()

            print(f"Player {player.name}: O-line points = {o_line_points}, D-line points = {d_line_points}")

            # Add player to respective lists based on participation
            if o_line_points > 0:
                o_line_candidates.append(player)
            if d_line_points > 0:
                d_line_candidates.append(player)

        print(f"Found {len(o_line_candidates)} O-line candidates")
        print(f"Found {len(d_line_candidates)} D-line candidates")

        # Calculate efficiency for each line
        def calculate_line_efficiency(players, is_offensive=True):
            """Calculate line efficiency with gender separation"""
            player_efficiency = {}
            for player in players:
                # Get points where player was in lineup
                lineup_query = LineUp.query.join(Point).filter(
                    LineUp.player_id == player.id,
                    Point.our_line_type == ('O-line' if is_offensive else 'D-line')
                )
                
                points = lineup_query.all()
                points_played = len(points)
                
                if points_played > 0:
                    # Count points where we scored using the Point.we_scored property
                    points_scored = sum(1 for lineup in points if lineup.point.we_scored)
                    
                    # Calculate efficiency as scoring percentage
                    efficiency = points_scored / points_played
        
                    player_efficiency[player] = efficiency
        
                    print(f"{'O' if is_offensive else 'D'}-line efficiency for {player.name}: "
                          f"{efficiency:.2f} ({points_scored}/{points_played} points scored)")
        
            return sorted(player_efficiency.items(), key=lambda x: x[1], reverse=True)
        
        # Calculate efficiencies and get top players
        o_line_efficiency = calculate_line_efficiency(o_line_candidates, is_offensive=True)
        d_line_efficiency = calculate_line_efficiency(d_line_candidates, is_offensive=False)
        
        # Separate players by gender with fallback
        o_line_women = [player for player, _ in o_line_efficiency if getattr(player, 'gender', '') == 'female'][:4]
        o_line_men = [player for player, _ in o_line_efficiency if getattr(player, 'gender', '') == 'male'][:4]
        d_line_women = [player for player, _ in d_line_efficiency if getattr(player, 'gender', '') == 'female'][:4]
        d_line_men = [player for player, _ in d_line_efficiency if getattr(player, 'gender', '') == 'male'][:4]
        
        # If we don't have enough players with gender data, fall back to the original method
        if not o_line_women and not o_line_men:
            print("Warning: No players with gender data found for O-line, using top players regardless of gender")
            o_line_players = [player for player, _ in o_line_efficiency][:7]
        else:
            o_line_players = o_line_women + o_line_men
        
        if not d_line_women and not d_line_men:
            print("Warning: No players with gender data found for D-line, using top players regardless of gender")
            d_line_players = [player for player, _ in d_line_efficiency][:7]
        else:
            d_line_players = d_line_women + d_line_men
        
                
        # Create combined lists for template
        o_line_players = o_line_women + o_line_men
        d_line_players = d_line_women + d_line_men


        # After calculating o_line_women, o_line_men, d_line_women, d_line_men
        print(f"O-line women: {[p.name for p in o_line_women]}")
        print(f"O-line men: {[p.name for p in o_line_men]}")
        print(f"D-line women: {[p.name for p in d_line_women]}")
        print(f"D-line men: {[p.name for p in d_line_men]}")
        

        # Generate heatmap data
        throws_query = Throw.query
        if team_name:
            throws_query = throws_query.join(Throw.thrower).filter(Player.team == team_name)
        
        throws = throws_query.all()
        heatmap_data = []
        
        # Process throws for heatmap
        for throw in throws:
            if throw.x_start is not None and throw.y_start is not None:
                throw_type = 'throwaway' if throw.throw_type == 'throwaway' else 'throw_start'
                heatmap_data.append({
                    'x': throw.x_start,
                    'y': throw.y_start,
                    'value': 1,
                    'type': throw_type
                })
                
                if throw.throw_type == 'assist' and throw.x_end is not None and throw.y_end is not None:
                    heatmap_data.append({
                        'x': throw.x_end,
                        'y': throw.y_end,
                        'value': 1,
                        'type': 'goal'
                    })

        # Add scored-on events
        scored_on_query = Event.query.filter_by(event_type='scored_on')
        if team_name:
            scored_on_query = scored_on_query.join(Event.player).filter(Player.team == team_name)
        
        for event in scored_on_query.all():
            if event.field_position_x is not None and event.field_position_y is not None:
                heatmap_data.append({
                    'x': event.field_position_x,
                    'y': event.field_position_y,
                    'value': 1,
                    'type': 'scored_on'
                })

        # Generate connection data
        connection_data = {
            'nodes': [],
            'links': []
        }
        
        players_in_connections = set()
        connections = {}
        
        for throw in throws:
            if throw.receiver_id:
                players_in_connections.add(throw.thrower_id)
                players_in_connections.add(throw.receiver_id)
                
                key = f"{throw.thrower_id}-{throw.receiver_id}"
                if key in connections:
                    connections[key]['value'] += 1
                else:
                    connections[key] = {
                        'source': throw.thrower_id,
                        'target': throw.receiver_id,
                        'value': 1
                    }
        
        for player_id in players_in_connections:
            player = Player.query.get(player_id)
            if player:
                connection_data['nodes'].append({
                    'id': player.id,
                    'name': player.name,
                    'jersey_number': player.jersey_number,
                    'position': player.position
                })
        
        connection_data['links'] = list(connections.values())

        return render_template(
            'stats/index.html',
            team_summary=team_summary,
            players=players,
            recent_games=recent_games,
            team_stats=team_stats,
            player_stats=player_stats,
            o_line_players=o_line_players,
            d_line_players=d_line_players,
            o_line_women=o_line_women,
            o_line_men=o_line_men,
            d_line_women=d_line_women,
            d_line_men=d_line_men,
            o_line_efficiency=dict(o_line_efficiency),
            d_line_efficiency=dict(d_line_efficiency),
            heatmap_data=json.dumps(heatmap_data),
            connection_data=json.dumps(connection_data)
        )

    except Exception as e:
        print(f"Error in index route: {str(e)}")
        flash(f"An error occurred: {str(e)}", "danger")
        return render_template('stats/index.html', **default_context)






# Add these helper functions:

def calculate_player_recent_performance(player, recent_games):
    """Calculate player's performance trends over recent games"""
    performance = []
    for game in recent_games:
        game_stats = get_player_base_stats(player, game)
        if game_stats['points_played'] > 0:
            performance.append({
                'date': game.date,
                'per': calculate_per(player, game, calculate_team_averages([game])),
                'plus_minus': (game_stats['goals'] + game_stats['assists'] + 
                             game_stats['blocks'] - game_stats['turnovers'])
            })
    return performance

def calculate_performance_trends(games):
    """Calculate team performance trends over time"""
    if not games:
        return {
            'dates': [],
            'o_line_efficiency': [],
            'd_line_efficiency': [],
            'break_percentage': []
        }
    
    # Sort games by date
    sorted_games = sorted(games, key=lambda g: g.date if g.date else datetime.min)
    
    # Calculate metrics for each game
    dates = []
    o_line_efficiency = []
    d_line_efficiency = []
    break_percentage = []
    
    for game in sorted_games:
        if game.date:
            dates.append(game.date.strftime('%Y-%m-%d'))
        else:
            dates.append('Unknown')
        
        # Calculate O-line efficiency - handle both query objects and lists
        try:
            # If game.o_line_points is a query object
            o_points = game.o_line_points.all()
        except AttributeError:
            # If game.o_line_points is already a list
            o_points = game.o_line_points
        
        o_points_count = len(o_points)
        o_conversions = sum(1 for p in o_points if p.we_scored)
        o_line_efficiency.append((o_conversions / o_points_count * 100) if o_points_count > 0 else 0)
        
        # Calculate D-line efficiency - handle both query objects and lists
        try:
            # If game.d_line_points is a query object
            d_points = game.d_line_points.all()
        except AttributeError:
            # If game.d_line_points is already a list
            d_points = game.d_line_points
        
        d_points_count = len(d_points)
        d_conversions = sum(1 for p in d_points if p.we_scored)
        d_line_efficiency.append((d_conversions / d_points_count * 100) if d_points_count > 0 else 0)
        
        # Calculate break percentage - handle both query objects and lists
        try:
            # If game.points is a query object
            all_points = game.points.all()
        except AttributeError:
            # If game.points is already a list
            all_points = game.points
        
        total_points = len(all_points)
        breaks = sum(1 for p in all_points if p.is_break)
        break_percentage.append((breaks / total_points * 100) if total_points > 0 else 0)
    
    return {
        'dates': json.dumps(dates),
        'o_line_efficiency': json.dumps(o_line_efficiency),
        'd_line_efficiency': json.dumps(d_line_efficiency),
        'break_percentage': json.dumps(break_percentage)
    }



@bp.route('/player/<int:player_id>')
@login_required
def player_stats(player_id):
    player = Player.query.get_or_404(player_id)
    
    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    game_id = request.args.get('game_id', type=int)

    # Determine which games to analyze
    if game_id:
        games = [Game.query.get(game_id)] if Game.query.get(game_id) else []
    elif tournament_id:
        tournament = Tournament.query.get(tournament_id)
        games = tournament.games.all() if tournament else []
    else:
        games = Game.query.all()

    # Get point IDs for filtering if games are selected
    point_ids = [p.id for g in games for p in g.points] if games else None

    # Query throws
    throws_query = Throw.query.filter_by(thrower_id=player_id)
    if point_ids:
        throws_query = throws_query.filter(Throw.point_id.in_(point_ids))
    
    throws = throws_query.order_by(Throw.created_at).all()
    print(f"Found {len(throws)} throws for player")

    # Generate throw vectors
    throw_vectors = []
    normalized_vectors = []
    for throw in throws:
        if (throw.x_start is not None and throw.y_start is not None and 
            throw.x_end is not None and throw.y_end is not None):
            
            # Regular vector
            vector = {
                'start_x': throw.x_start,
                'start_y': throw.y_start,
                'end_x': throw.x_end,
                'end_y': throw.y_end,
                'type': throw.throw_type,
                'distance': throw.calculate_distance(),
                'is_completion': "true" if throw.is_completion else "false"  # Convert to string
            }
            throw_vectors.append(vector)

            # Normalized vector (centered on field)
            center_x, center_y = 50, 18.5  # Center of field
            dx = throw.x_end - throw.x_start
            dy = throw.y_end - throw.y_start
            distance = throw.calculate_distance()
            if distance:
                scale = 20 / distance  # Standardize to 20 meters length
                normalized_vector = {
                    'start_x': center_x,
                    'start_y': center_y,
                    'end_x': center_x + (dx * scale),
                    'end_y': center_y + (dy * scale),
                    'type': throw.throw_type,
                    'distance': distance,
                    'is_completion': throw.is_completion
                }
                normalized_vectors.append(normalized_vector)

    print(f"Generated {len(throw_vectors)} throw vectors")
    print("Sample vector:", throw_vectors[0] if throw_vectors else "No vectors")

    # Get throwaway locations
    throwaway_throws = throws_query.filter_by(throw_type='throwaway').all()
    throwaway_locations = []
    
    for throw in throwaway_throws:
        if throw.x_start is not None and throw.y_start is not None:
            location = {
                'x': throw.x_end,  # For throwaways, reception position is where the throw ended
                'y': throw.y_end,
                'prev_x': throw.x_start,  # Throw position is where it started
                'prev_y': throw.y_start
            }
            throwaway_locations.append(location)

    print(f"Generated {len(throwaway_locations)} throwaway locations")
    print("Sample throwaway:", throwaway_locations[0] if throwaway_locations else "No throwaways")

    # Calculate regular stats
    stats = get_player_base_stats(player, games)
    
    # Calculate team averages specifically for these games
    team_avgs = calculate_team_averages(games)
    
    if stats['points_played'] > 0:
        stats['per'] = calculate_per(player, games, team_avgs)
    
    # Add hucks to player stats
    stats['hucks'] = calculate_hucks(player, games)
    
    # Add shutdowns calculation (if not already included)
    stats['shutdowns'] = count_events(
        Event.query.filter_by(player_id=player.id),
        ['shutdown']
    )
    
    # Calculate team averages for radar charts
    team_stats = calculate_team_radar_stats(games, player.team)
    
    # Get player's game history
    player_games = []
    games_query = Game.query
    if tournament_id:
        games_query = games_query.filter_by(tournament_id=tournament_id)
    elif game_id:
        games_query = games_query.filter_by(id=game_id)
    
    for game in games_query.order_by(Game.date.desc()).all():
        if any(player.id in [lineup.player_id for lineup in point.lineups] 
              for point in game.points):
            game_stats = get_player_base_stats(player, game)
            # Calculate game-specific team averages
            game_team_avgs = calculate_team_averages([game])
            game_stats['per'] = calculate_per(
                player, game, 
                game_team_avgs
            )
            player_games.append({
                'game': game,
                'stats': game_stats
            })

    # Get tournaments for filter
    tournaments = Tournament.query.order_by(Tournament.start_date.desc()).all()

    # Calculate throw statistics
    throw_stats = {
        'total_throws': len(throws),
        'completions': len([t for t in throws if t.is_completion]),
        'assists': len([t for t in throws if t.throw_type == 'assist']),
        'hockey_assists': len([t for t in throws if t.throw_type == 'hockey_assist']),
        'average_distance': (sum(t.calculate_distance() or 0 for t in throws) / 
                           len(throws) if throws else 0)
    }

    total_distance = sum(vector['distance'] for vector in throw_vectors)
    avg_distance = total_distance / len(throw_vectors) if throw_vectors else 0

    # Get throw directions from player stats
    throw_directions = stats.get('throw_directions', {
        'E': 0, 'ENE': 0, 'NE': 0, 'NNE': 0, 
        'N': 0, 'NNW': 0, 'NW': 0, 'WNW': 0, 
        'W': 0, 'WSW': 0, 'SW': 0, 'SSW': 0, 
        'S': 0, 'SSE': 0, 'SE': 0, 'ESE': 0
    })
    
    # Get completion by direction from player stats
    completion_by_direction = stats.get('completion_by_direction', {
        'E': 0, 'ENE': 0, 'NE': 0, 'NNE': 0, 
        'N': 0, 'NNW': 0, 'NW': 0, 'WNW': 0, 
        'W': 0, 'WSW': 0, 'SW': 0, 'SSW': 0, 
        'S': 0, 'SSE': 0, 'SE': 0, 'ESE': 0
    })

    
    # Process throw vectors to get directional completion data
    for throw in throws:
        if (throw.x_start is not None and throw.y_start is not None and 
            throw.x_end is not None and throw.y_end is not None and 
            throw.is_completion):
            
            # Calculate angle
            dx = throw.x_end - throw.x_start
            dy = throw.y_end - throw.y_start
            angle = math.atan2(dy, dx)

            # Convert to degrees, adjust for clockwise from North, normalize
            degrees = (90 - math.degrees(angle)) % 360
                
            # Map angle to direction
            direction = None
            if degrees >= 337.5 or degrees < 22.5:
                direction = 'N'
            elif degrees >= 22.5 and degrees < 67.5:
                direction = 'NE'
            elif degrees >= 67.5 and degrees < 112.5:
                direction = 'E'
            elif degrees >= 112.5 and degrees < 157.5:
                direction = 'SE'
            elif degrees >= 157.5 and degrees < 202.5:
                direction = 'S'
            elif degrees >= 202.5 and degrees < 247.5:
                direction = 'SW'
            elif degrees >= 247.5 and degrees < 292.5:
                direction = 'W'
            else:
                direction = 'NW'
                
            completion_by_direction[direction] += 1

    return render_template(
        'stats/player_stats.html',
        player=player,
        stats=stats,
        team_stats=team_stats,
        player_games=player_games,
        tournaments=tournaments,
        selected_tournament=tournament_id,
        selected_game=game_id,
        throw_vectors=throw_vectors,
        normalized_vectors=normalized_vectors,
        throwaway_locations=throwaway_locations,
        throw_stats=throw_stats,
        total_throw_distance=total_distance,
        avg_throw_distance=avg_distance,
        throw_directions=throw_directions,
        completion_by_direction=completion_by_direction
    )






@bp.route('/game/<int:game_id>')
@login_required
def game_stats(game_id):
    """
    Comprehensive game statistics and visualizations
    """
    game = Game.query.get_or_404(game_id)
    
    # Calculate team statistics
    team_stats = calculate_game_stats(game)
    
    # Calculate player statistics for this game
    player_stats = []
    players_in_game = set()
    
    for point in game.points:
        for lineup in point.lineups:
            players_in_game.add(lineup.player)
    
    team_avgs = calculate_team_averages([game])
    
    for player in players_in_game:
        stats = get_player_base_stats(player, game)
        stats['per'] = calculate_per(player, game, team_avgs)
        player_stats.append({
            'player': player,
            'stats': stats
        })
    
    # Sort by points played
    player_stats.sort(key=lambda x: x['stats']['points_played'], reverse=True)
    
    # Generate visualization data
    events = []
    for point in game.points:
        events.extend(point.events.all())
    
    heatmap_data = process_heatmap_data(events)
    connection_data = generate_player_connections(events)
    
    return render_template(
        'stats/game_stats.html',
        game=game,
        team_stats=team_stats,
        player_stats=player_stats,
        heatmap_data=json.dumps(heatmap_data),
        connections=json.dumps(connection_data)
    )

@bp.route('/team')
@login_required
def team_stats():
    """
    Team-level statistics and analysis
    """
    # Get filter parameters
    season = request.args.get('season', '')
    tournament_id = request.args.get('tournament_id', type=int)
    
    # Get filtered games
    games_query = Game.query
    if tournament_id:
        games_query = games_query.filter_by(tournament_id=tournament_id)
    elif season:
        tournament_ids = [t.id for t in Tournament.query.filter_by(season=season).all()]
        games_query = games_query.filter(Game.tournament_id.in_(tournament_ids))
    
    games = games_query.order_by(Game.date).all()
    
    # Calculate team summary stats
    team_summary = calculate_team_summary(games)
    
    # Add additional metrics for radar charts
    team_summary.update(calculate_additional_team_metrics(games))
    
    # Calculate previous period stats for comparison
    # (e.g., previous season or previous tournament)
    prev_games = get_previous_period_games(season, tournament_id)
    prev_summary = calculate_team_summary(prev_games)
    prev_metrics = calculate_additional_team_metrics(prev_games)
    
    # Add previous metrics with 'prev_' prefix
    for key, value in prev_metrics.items():
        team_summary[f'prev_{key}'] = value
    for key, value in prev_summary.items():
        if key not in team_summary:
            team_summary[f'prev_{key}'] = value
    
    # Calculate player statistics
    players = Player.query.filter_by(active=True).all()
    team_avgs = calculate_team_averages(games)
    
    player_stats = []
    for player in players:
        stats = get_player_base_stats(player, games)
        if stats['points_played'] > 0:
            stats['per'] = calculate_per(player, games, team_avgs)
            player_stats.append({
                'player': player,
                'stats': stats
            })
    
    # Sort by PER
    player_stats.sort(key=lambda x: x['stats']['per'], reverse=True)
    
    # Calculate line efficiency with gender separation
    o_line_efficiency = calculate_line_efficiency(players, games, is_offensive=True)
    d_line_efficiency = calculate_line_efficiency(players, games, is_offensive=False)
    
    # Separate players by gender
    o_line_women = [player for player, _ in o_line_efficiency if getattr(player, 'gender', '') == 'female'][:4]
    o_line_men = [player for player, _ in o_line_efficiency if getattr(player, 'gender', '') == 'male'][:4]
    d_line_women = [player for player, _ in d_line_efficiency if getattr(player, 'gender', '') == 'female'][:4]
    d_line_men = [player for player, _ in d_line_efficiency if getattr(player, 'gender', '') == 'male'][:4]
    
    # If we don't have enough players with gender data, fall back to the original method
    if not o_line_women and not o_line_men:
        o_line_players = [player for player, _ in o_line_efficiency][:7]
    else:
        o_line_players = o_line_women + o_line_men
    
    if not d_line_women and not d_line_men:
        d_line_players = [player for player, _ in d_line_efficiency][:7]
    else:
        d_line_players = d_line_women + d_line_men
    
    # Calculate performance trends
    performance_trends = calculate_performance_trends(games)
    
    # Get filter options
    tournaments = Tournament.query.order_by(Tournament.start_date.desc()).all()
    seasons = db.session.query(Tournament.season).distinct().all()
    seasons = [s[0] for s in seasons if s[0]]
    
    return render_template(
        'stats/team_stats.html',
        player_stats=player_stats,
        team_summary=team_summary,
        tournaments=tournaments,
        seasons=seasons,
        selected_tournament=tournament_id,
        selected_season=season,
        o_line_players=o_line_players,
        d_line_players=d_line_players,
        o_line_women=o_line_women,
        o_line_men=o_line_men,
        d_line_women=d_line_women,
        d_line_men=d_line_men,
        o_line_efficiency=dict(o_line_efficiency),
        d_line_efficiency=dict(d_line_efficiency),
        performance_trends=performance_trends
    )


# --- Helper functions for visualization data ---

def generate_throw_vectors(player, games=None):
    """Generate throw vector data based on consecutive catches"""
    events_query = Event.query.filter(
        Event.player_id == player.id,
        Event.event_type.in_(['catch', 'goal'])
    )

    if games:
        if isinstance(games, list):
            point_ids = [p.id for g in games for p in g.points]
        else:
            point_ids = [p.id for p in games.points]
        events_query = events_query.filter(Event.point_id.in_(point_ids))

    throw_vectors = []
    for event in events_query.all():
        if event.previous_catch_id:
            previous_catch = Event.query.get(event.previous_catch_id)
            if previous_catch:
                throw_vectors.append({
                    'start_x': previous_catch.field_position_x,
                    'start_y': previous_catch.field_position_y,
                    'end_x': event.field_position_x,
                    'end_y': event.field_position_y,
                    'distance': event.inferred_throw_distance,
                    'direction': event.inferred_throw_direction
                })

    return throw_vectors



def generate_throwaway_locations(player, games=None):
    """
    Generate throwaway location data for visualization
    """
    events_query = Event.query.filter_by(player_id=player.id, event_type='throwaway')
    if games:
        if isinstance(games, list):
            point_ids = [p.id for g in games for p in g.points]
        else:
            point_ids = [p.id for p in games.points]
        events_query = events_query.filter(Event.point_id.in_(point_ids))
    
    throwaway_locations = []
    for event in events_query.all():
        if event.field_position_x is not None and event.field_position_y is not None:
            location_data = {
                'x': event.field_position_x,
                'y': event.field_position_y
            }
            
            # Try to find the previous event to show throw trajectory
            prev_event = Event.query.filter(
                Event.point_id == event.point_id,
                Event.timestamp < event.timestamp
            ).order_by(Event.timestamp.desc()).first()
            
            if prev_event and prev_event.field_position_x is not None and prev_event.field_position_y is not None:
                location_data.update({
                    'prev_x': prev_event.field_position_x,
                    'prev_y': prev_event.field_position_y
                })
            
            throwaway_locations.append(location_data)
    
    return throwaway_locations

def count_points_played(player, games=None):
    """Count number of points played by a player"""
    query = LineUp.query.filter_by(player_id=player.id)
    if games:
        if isinstance(games, list):
            point_ids = [p.id for g in games for p in g.points]
        else:
            point_ids = [p.id for p in games.points]
        query = query.filter(LineUp.point_id.in_(point_ids))
    return query.count()

def count_events(query_base, event_types):
    """Count events of specific types from a base query"""
    return query_base.filter(Event.event_type.in_(event_types)).count()

def calculate_completion_rate(stats):
    """Calculate completion rate from stats dictionary"""
    total_throws = stats['completions'] + stats.get('throwaways', 0)
    return (stats['completions'] / total_throws * 100) if total_throws > 0 else 0

def calculate_catch_rate(stats):
    """Calculate catch rate from stats dictionary"""
    total_catches = stats['catches'] + stats.get('drops', 0)
    return (stats['catches'] / total_catches * 100) if total_catches > 0 else 0

def calculate_o_d_line_stats(player, games=None):
    """Calculate O-line and D-line statistics"""
    stats = {
        'o_line_points_played': 0,
        'd_line_points_played': 0,
        'o_line_plus_minus': 0,
        'd_line_plus_minus': 0,
        'o_line_plus_minus_per_point': 0,
        'd_line_plus_minus_per_point': 0  # Added these two fields
    }

    try:
        query = LineUp.query.filter_by(player_id=player.id).join(Point)
        if games:
            if isinstance(games, list):
                game_ids = [g.id for g in games]
            else:
                game_ids = [games.id]
            query = query.filter(Point.game_id.in_(game_ids))

        o_line_points = query.filter(Point.our_line_type == 'O-line').all()
        d_line_points = query.filter(Point.our_line_type == 'D-line').all()

        stats['o_line_points_played'] = len(o_line_points)
        stats['d_line_points_played'] = len(d_line_points)

        for point in o_line_points:
            plus_minus = calculate_point_plus_minus(point)
            stats['o_line_plus_minus'] += plus_minus
        
        for point in d_line_points:
            plus_minus = calculate_point_plus_minus(point)
            stats['d_line_plus_minus'] += plus_minus

        # Calculate per point stats
        stats['o_line_plus_minus_per_point'] = (
            stats['o_line_plus_minus'] / stats['o_line_points_played'] 
            if stats['o_line_points_played'] > 0 else 0
        )
        
        stats['d_line_plus_minus_per_point'] = (
            stats['d_line_plus_minus'] / stats['d_line_points_played']
            if stats['d_line_points_played'] > 0 else 0
        )

    except Exception as e:
        print(f"Error calculating O/D line stats for player {player.id}: {str(e)}")

    return stats

def calculate_point_plus_minus(point):
    """Calculate plus/minus for a single point with null checking"""
    try:
        our_score_before = point.our_score_before or 0
        our_score_after = point.our_score_after or 0
        their_score_before = point.their_score_before or 0
        their_score_after = point.their_score_after or 0
        
        return (our_score_after - our_score_before) - (
            their_score_after - their_score_before
        )
    except AttributeError:
        return 0


def calculate_team_summary(games):
    """Calculate team summary statistics"""
    summary = {
        'games_played': len(games),
        'wins': sum(1 for g in games if g.is_win),
        'losses': sum(1 for g in games if g.is_loss),
        'ties': sum(1 for g in games if g.is_tie),
        'total_points': sum(len(g.points.all()) for g in games),
        'o_line_points': 0,
        'o_line_conversions': 0,
        'd_line_points': 0,
        'd_line_conversions': 0,
        'breaks': 0,
        'holds': 0
    }

    for game in games:
        o_points = game.o_line_points
        d_points = game.d_line_points
        
        summary['o_line_points'] += len(o_points)
        summary['o_line_conversions'] += sum(1 for p in o_points if p.we_scored)
        summary['d_line_points'] += len(d_points)
        summary['d_line_conversions'] += sum(1 for p in d_points if p.we_scored)
        summary['breaks'] += sum(1 for p in game.points if p.is_break)
        summary['holds'] += sum(1 for p in game.points if p.is_hold)

    summary['win_percentage'] = (
        (summary['wins'] / summary['games_played'] * 100) 
        if summary['games_played'] > 0 else 0
    )
    summary['o_line_conversion_rate'] = (
        (summary['o_line_conversions'] / summary['o_line_points'] * 100)
        if summary['o_line_points'] > 0 else 0
    )
    summary['d_line_conversion_rate'] = (
        (summary['d_line_conversions'] / summary['d_line_points'] * 100)
        if summary['d_line_points'] > 0 else 0
    )

    return summary

def calculate_unadjusted_per(stats):
    """
    Calculate raw unadjusted PER without normalization
    """
    if stats['points_played'] == 0:
        return 0
        
    # Define weights
    WEIGHTS = {
        'scoring': 0.5,
        'assist': 0.5,
        'turnover': -0.75,
        'defense': 0.75,
        'throw': 0.05,
        'plus_minus': 0.1
    }

    # Calculate raw PER
    uper = (1 / stats['points_played']) * (
        (WEIGHTS['scoring'] * (stats['goals'] ** 0.75)) +
        (WEIGHTS['assist'] * (stats['assists'] ** 0.75)) +
        (WEIGHTS['assist'] * 0.5 * (stats['hockey_assists'] ** 0.75)) +
        (WEIGHTS['turnover'] * ((stats['throwaways'] + stats['drops']) ** 0.75)) +
        (WEIGHTS['defense'] * (stats['blocks'] ** 0.75)) +
        (WEIGHTS['throw'] * (
            (stats['completions'] ** 0.75) * ((stats['completion_rate']/100) ** 3.0) +
            (stats['catches'] ** 0.75) * ((stats['catch_rate']/100) ** 3.0)
        )) +
        (WEIGHTS['plus_minus'] * (
            stats.get('o_line_plus_minus_per_point', 0) + 
            stats.get('d_line_plus_minus_per_point', 0)
        ))
    )
    
    return uper


def normalize_per(value):
    """Normalize PER to a 0-30 scale"""
    return min(max(value, 0), 100)

def count_possessions(events):
    """Count number of possessions in a sequence of events"""
    possessions = 1
    current_team = True  # True for our team, False for opponent

    for event in events:
        if event.event_type in ['throwaway', 'drop', 'stall']:
            if current_team:
                current_team = False
                possessions += 1
        elif event.event_type == 'block':
            if not current_team:
                current_team = True
                possessions += 1

    return possessions



def get_optimal_lines(points, players):
    """Calculate optimal lines based on actual performance"""
    o_line_performances = {}
    d_line_performances = {}
    
    for point in points:
        # Get the players who were on this point
        point_players = [lineup.player for lineup in point.lineups]
        
        # Calculate success rate for this combination
        success = point.point_outcome == 'scored'
        
        if point.our_line_type == 'O-line':
            key = tuple(sorted(p.id for p in point_players))
            if key not in o_line_performances:
                o_line_performances[key] = {'players': point_players, 'success': 0, 'total': 0}
            o_line_performances[key]['success'] += 1 if success else 0
            o_line_performances[key]['total'] += 1
        else:
            key = tuple(sorted(p.id for p in point_players))
            if key not in d_line_performances:
                d_line_performances[key] = {'players': point_players, 'success': 0, 'total': 0}
            d_line_performances[key]['success'] += 1 if success else 0
            d_line_performances[key]['total'] += 1
    
    # Sort by success rate
    best_o_line = sorted(
        o_line_performances.values(),
        key=lambda x: (x['success'] / x['total'] if x['total'] > 0 else 0),
        reverse=True
    )
    
    best_d_line = sorted(
        d_line_performances.values(),
        key=lambda x: (x['success'] / x['total'] if x['total'] > 0 else 0),
        reverse=True
    )
    
    return (
        best_o_line[0]['players'] if best_o_line else [],
        best_d_line[0]['players'] if best_d_line else []
    )

@bp.route('/debug_stats/<int:player_id>')
@login_required
def debug_stats(player_id):
    player = Player.query.get_or_404(player_id)
    point_stats = PlayerPointStats.query.filter_by(player_id=player_id).all()
    events = Event.query.filter_by(player_id=player_id).all()
    
    return jsonify({
        'player': player.name,
        'num_point_stats': len(point_stats),
        'num_events': len(events),
        'point_stats': [{
            'point_id': ps.point_id,
            'o_line_plus_minus': ps.o_line_plus_minus,
            'd_line_plus_minus': ps.d_line_plus_minus
        } for ps in point_stats],
        'events': [{
            'event_type': e.event_type,
            'point_id': e.point_id,
            'is_offensive': e.is_offensive
        } for e in events]
    })


### 07/2025 Update Radar Chart

def calculate_hucks(player, games=None):
    """Calculate number of hucks (throws over 20m)"""
    query = Throw.query.filter_by(thrower_id=player.id)
    
    if games:
        if isinstance(games, list):
            point_ids = [p.id for g in games for p in g.points]
        else:
            point_ids = [p.id for p in games.points]
        query = query.filter(Throw.point_id.in_(point_ids))
    
    # Count throws with distance > 20m
    hucks = 0
    for throw in query.all():
        distance = throw.calculate_distance()
        if distance and distance > 20:
            hucks += 1
    
    return hucks


@bp.route('/debug/players')
@login_required
def debug_players():
    players = Player.query.filter_by(active=True).all()
    return jsonify({
        'players': [{
            'id': p.id,
            'name': p.name,
            'gender': getattr(p, 'gender', None),
            'position': getattr(p, 'position', None)
        } for p in players]
    })

@bp.route('/debug/break_throws')
@login_required
def debug_break_throws():
    # Get all throws with break_throw=True
    break_throws = Throw.query.filter_by(break_throw=True).all()
    
    # Get total throws for comparison
    total_throws = Throw.query.count()
    
    return jsonify({
        'total_throws': total_throws,
        'break_throws': len(break_throws),
        'percentage': (len(break_throws) / total_throws * 100) if total_throws > 0 else 0,
        'sample_break_throws': [{
            'id': t.id,
            'thrower_id': t.thrower_id,
            'thrower_name': t.thrower.name if t.thrower else 'Unknown',
            'point_id': t.point_id,
            'throw_type': t.throw_type,
            'is_completion': t.is_completion
        } for t in break_throws[:10]]  # Show first 10 break throws
    })


@bp.route('/debug/per/<int:player_id>')
@login_required
def debug_per_calculation(player_id):
    """Debug page showing step-by-step PER calculation for a player"""
    player = Player.query.get_or_404(player_id)
    
    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    game_id = request.args.get('game_id', type=int)

    # Determine which games to analyze
    if game_id:
        games = [Game.query.get(game_id)] if Game.query.get(game_id) else []
    elif tournament_id:
        tournament = Tournament.query.get(tournament_id)
        games = tournament.games.all() if tournament else []
    else:
        games = Game.query.all()
    
    # Get player stats
    stats = get_player_base_stats(player, games)
    
    # Calculate team averages
    team_avgs = calculate_team_averages(games)
    
    # Calculate raw PER values for all players to find max
    all_players = Player.query.filter_by(active=True).all()
    raw_per_values = {}
    
    for p in all_players:
        p_stats = get_player_base_stats(p, games)
        if p_stats['points_played'] > 0:
            # Calculate raw PER without final normalization
            raw_per = calculate_unadjusted_per(p_stats)
            # Scale to league average of 15
            avg_uper = team_avgs.get('avg_uper', 1)
            if avg_uper <= 0:
                avg_uper = 1
            scaled_per = raw_per * (15 / avg_uper)
            raw_per_values[p.id] = scaled_per
    
    # Find max PER value
    max_per = max(raw_per_values.values()) if raw_per_values else 30
    
    # Calculate step-by-step PER components
    debug_info = {}
    
    if stats['points_played'] > 0:
        # Define weights
        WEIGHTS = {
            'scoring': 0.5,
            'assist': 0.5,
            'turnover': -0.75,
            'defense': 0.75,
            'throw': 0.05,
            'plus_minus': 0.1
        }
        
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
        
        # Plus-minus component calculations
        o_line_pm = stats.get('o_line_plus_minus_per_point', 0) - team_avgs.get('avg_o_line_plus_minus_per_point', 0)
        d_line_pm = stats.get('d_line_plus_minus_per_point', 0) - team_avgs.get('avg_d_line_plus_minus_per_point', 0)
        plus_minus_component = WEIGHTS['plus_minus'] * (o_line_pm + d_line_pm)
        
        # Raw unadjusted PER
        raw_uper = (1 / stats['points_played']) * (box_component + passing_component + plus_minus_component)
        
        # Scale to league average of 15
        avg_uper = team_avgs.get('avg_uper', 1)
        if avg_uper <= 0:
            avg_uper = 1
        scaled_per = raw_uper * (15 / avg_uper)
        
        # Normalize to 0-100 scale
        final_per = (scaled_per / max_per) * 100 if max_per > 0 else 0
        
        # Store all calculation steps
        debug_info = {
            'raw_stats': {
                'points_played': stats['points_played'],
                'goals': stats['goals'],
                'assists': stats['assists'],
                'hockey_assists': stats['hockey_assists'],
                'blocks': stats['blocks'],
                'throwaways': stats['throwaways'],
                'drops': stats['drops'],
                'stalls': stats.get('stalls', 0),
                'callahans': stats.get('callahans', 0),
                'completions': stats['completions'],
                'completion_rate': stats['completion_rate'],
                'catches': stats['catches'],
                'catch_rate': stats['catch_rate'],
                'o_line_plus_minus_per_point': stats.get('o_line_plus_minus_per_point', 0),
                'd_line_plus_minus_per_point': stats.get('d_line_plus_minus_per_point', 0)
            },
            'team_avgs': {
                'avg_uper': team_avgs.get('avg_uper', 0),
                'avg_o_line_plus_minus_per_point': team_avgs.get('avg_o_line_plus_minus_per_point', 0),
                'avg_d_line_plus_minus_per_point': team_avgs.get('avg_d_line_plus_minus_per_point', 0)
            },
            'weights': WEIGHTS,
            'box_component': {
                'goals': goals_component,
                'assists': assists_component,
                'hockey_assists': hockey_assists_component,
                'turnovers': turnovers_component,
                'blocks': blocks_component,
                'stalls': stalls_component,
                'callahans': callahans_component,
                'total': box_component
            },
            'passing_component': {
                'completion_factor': completion_factor,
                'catch_factor': catch_factor,
                'completions': completions_component,
                'catches': catches_component,
                'total': passing_component
            },
            'plus_minus_component': {
                'o_line': o_line_pm,
                'd_line': d_line_pm,
                'total': plus_minus_component
            },
            'calculation': {
                'raw_uper': raw_uper,
                'avg_uper': avg_uper,
                'scaled_per': scaled_per,
                'max_per': max_per,
                'final_per': final_per
            },
            'top_players': {
                'player_id': [p.id for p in all_players if p.id in raw_per_values][:10],
                'player_name': [p.name for p in all_players if p.id in raw_per_values][:10],
                'raw_per': [raw_per_values[p.id] for p in all_players if p.id in raw_per_values][:10]
            }
        }
    
    # Get tournaments for filter
    tournaments = Tournament.query.order_by(Tournament.start_date.desc()).all()
    
    return render_template(
        'stats/debug_per.html',
        player=player,
        stats=stats,
        debug_info=debug_info,
        tournaments=tournaments,
        selected_tournament=tournament_id,
        selected_game=game_id,
        games=games
    )

def calculate_additional_team_metrics(games):
    """Calculate additional team metrics for radar charts"""
    if not games:
        return {
            'completion_rate': 0,
            'goals_per_point': 0,
            'assists_per_point': 0,
            'throws_per_point': 0,
            'hucks_per_point': 0,
            'blocks_per_point': 0,
            'turnovers_forced_per_point': 0,
            'defensive_efficiency': 0,
            'break_percentage': 0
        }
    
    # Count total points - handle both query objects and lists
    total_points = 0
    for game in games:
        try:
            # If game.points is a query object
            points = game.points.all()
        except AttributeError:
            # If game.points is already a list
            points = game.points
        total_points += len(points)
    
    if total_points == 0:
        return {
            'completion_rate': 0,
            'goals_per_point': 0,
            'assists_per_point': 0,
            'throws_per_point': 0,
            'hucks_per_point': 0,
            'blocks_per_point': 0,
            'turnovers_forced_per_point': 0,
            'defensive_efficiency': 0,
            'break_percentage': 0
        }
    
    # Get point IDs for filtering
    point_ids = []
    for game in games:
        try:
            # If game.points is a query object
            points = game.points.all()
        except AttributeError:
            # If game.points is already a list
            points = game.points
        point_ids.extend([p.id for p in points])
    
    # Count all throws
    throws_query = Throw.query
    throws_query = throws_query.filter(Throw.point_id.in_(point_ids))
    throws = throws_query.all()
    
    # Count completions
    completions = sum(1 for t in throws if t.is_completion)
    
    # Count goals and assists
    goals = sum(1 for t in throws if t.throw_type == 'assist')
    
    # Count blocks
    blocks_query = Event.query.filter_by(event_type='block')
    blocks_query = blocks_query.filter(Event.point_id.in_(point_ids))
    blocks = blocks_query.count()
    
    # Count turnovers forced
    turnovers_forced_query = Event.query.filter(
        Event.event_type.in_(['throwaway', 'drop', 'stall']),
        Event.is_offensive == False
    )
    turnovers_forced_query = turnovers_forced_query.filter(Event.point_id.in_(point_ids))
    turnovers_forced = turnovers_forced_query.count()
    
    # Count hucks
    hucks = sum(1 for t in throws if t.calculate_distance() and t.calculate_distance() > 20)
    
    # Calculate break percentage
    breaks = 0
    for game in games:
        try:
            # If game.points is a query object
            points = game.points.all()
        except AttributeError:
            # If game.points is already a list
            points = game.points
        breaks += sum(1 for p in points if p.is_break)
    break_percentage = (breaks / total_points) * 100
    
    # Calculate defensive efficiency
    d_points_count = 0
    d_conversions = 0
    for game in games:
        try:
            # If game.d_line_points is a query object
            d_points = game.d_line_points.all()
        except AttributeError:
            # If game.d_line_points is already a list
            d_points = game.d_line_points
        d_points_count += len(d_points)
        d_conversions += sum(1 for p in d_points if p.we_scored)
    defensive_efficiency = (d_conversions / d_points_count) * 100 if d_points_count > 0 else 0
    
    return {
        'completion_rate': (completions / len(throws)) * 100 if throws else 0,
        'goals_per_point': goals / total_points,
        'assists_per_point': goals / total_points,  # Same as goals
        'throws_per_point': len(throws) / total_points,
        'hucks_per_point': hucks / total_points,
        'blocks_per_point': blocks / total_points,
        'turnovers_forced_per_point': turnovers_forced / total_points,
        'defensive_efficiency': defensive_efficiency,
        'break_percentage': break_percentage
    }



def get_previous_period_games(season, tournament_id):
    """Get games from previous period for comparison"""
    if tournament_id:
        # Get current tournament
        current_tournament = Tournament.query.get(tournament_id)
        if current_tournament:
            # Find previous tournament in same season
            prev_tournament = Tournament.query.filter(
                Tournament.season == current_tournament.season,
                Tournament.start_date < current_tournament.start_date
            ).order_by(Tournament.start_date.desc()).first()
            
            if prev_tournament:
                return Game.query.filter_by(tournament_id=prev_tournament.id).all()
    elif season:
        # Get previous season
        seasons = db.session.query(Tournament.season).distinct().order_by(Tournament.season).all()
        seasons = [s[0] for s in seasons if s[0]]
        
        if season in seasons:
            idx = seasons.index(season)
            if idx > 0:
                prev_season = seasons[idx - 1]
                tournament_ids = [t.id for t in Tournament.query.filter_by(season=prev_season).all()]
                return Game.query.filter(Game.tournament_id.in_(tournament_ids)).all()
    
    # Default: return empty list if no previous period found
    return []

def calculate_line_efficiency(players, games, is_offensive=True):
    """Calculate line efficiency with gender separation"""
    player_efficiency = {}
    
    for player in players:
        # Get points where player was in lineup
        lineup_query = LineUp.query.join(Point).filter(
            LineUp.player_id == player.id,
            Point.our_line_type == ('O-line' if is_offensive else 'D-line')
        )
        
        if games:
            game_ids = [g.id for g in games]
            lineup_query = lineup_query.filter(Point.game_id.in_(game_ids))
        
        points = lineup_query.all()
        points_played = len(points)
        
        if points_played > 0:
            # Count points where we scored using the Point.we_scored property
            points_scored = sum(1 for lineup in points if lineup.point.we_scored)
            
            # Calculate efficiency as scoring percentage
            efficiency = points_scored / points_played

            player_efficiency[player] = efficiency

    return sorted(player_efficiency.items(), key=lambda x: x[1], reverse=True)

