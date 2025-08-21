from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from sqlalchemy.orm import subqueryload
from flask_login import login_required, current_user
from app import db
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.point import Point, LineUp
from app.models.event import Event
from app.models.stats import PlayerPointStats
from app.models.throws import Throw
from app.models.cutting_skill import CuttingSkill
from app.models.clip import Clip
import json
import math
from app.utils.utils import admin_required
from datetime import datetime, date
from functools import lru_cache
from datetime import datetime, timedelta


bp = Blueprint('stats_dashboard', __name__, url_prefix='/stats')

# Helper function to get current team ID
def get_current_team_id():
    if current_user.is_admin:
        return session.get('current_team_id')
    return current_user.team_organization_id

def is_admin(user):
    """Check if user has admin role"""
    return user.role == 'admin' if hasattr(user, 'role') else False

def is_coach(user):
    """Check if user has coach role"""
    return user.role == 'coach' if hasattr(user, 'role') else False

# Cache for team averages that rarely change
_team_avg_cache = {}
_team_avg_timestamp = {}

def get_cached_team_averages(games=None, max_age_minutes=15):
    """Get team averages with caching"""
    # Create a cache key based on game IDs and team ID
    team_id = get_current_team_id()
    if games:
        if isinstance(games, list):
            cache_key = (team_id, tuple(sorted([g.id for g in games])))
        else:
            cache_key = (team_id, (games.id,))
    else:
        cache_key = (team_id, 'all_games')
    
    now = datetime.now()
    if (cache_key in _team_avg_cache and 
        cache_key in _team_avg_timestamp and
        now - _team_avg_timestamp[cache_key] < timedelta(minutes=max_age_minutes)):
        print(f"Using cached team averages for {cache_key}")
        return _team_avg_cache[cache_key]
    
    # Calculate if not in cache or expired
    print(f"Calculating team averages for {cache_key}")
    result = calculate_team_averages(games)
    _team_avg_cache[cache_key] = result
    _team_avg_timestamp[cache_key] = now
    return result

def safe_date_format(date_obj, format_str='%Y-%m-%d'):
    """Safely format a date object, handling None values"""
    if date_obj and hasattr(date_obj, 'strftime'):
        return date_obj.strftime(format_str)
    elif date_obj:
        return str(date_obj)
    else:
        return "Unknown"


# Use LRU cache for player stats that don't change often
@lru_cache(maxsize=128)
def get_cached_player_base_stats(player_id, game_ids_tuple=None, team_id=None):
    """Cached version of player stats"""
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=team_id
    ).first()
    
    if not player:
        return {}
        
    if game_ids_tuple:
        games = [Game.query.filter_by(
            id=gid,
            team_organization_id=team_id
        ).first() for gid in game_ids_tuple]
        games = [g for g in games if g]  # Filter out None values
    else:
        games = None
        
    return get_player_base_stats(player, games)

# Helper function to convert games to a tuple of IDs for caching
def games_to_tuple(games):
    """Convert games to a tuple of IDs for use as cache key"""
    if not games:
        return None
    if isinstance(games, list):
        return tuple(sorted([g.id for g in games]))
    return (games.id,)

def invalidate_stats_cache(player_id=None, game_id=None):
    """Invalidate stats cache when data changes"""
    global _team_avg_cache, _team_avg_timestamp
    
    # If a specific player's stats changed
    if player_id:
        # Clear LRU cache for this player
        get_cached_player_base_stats.cache_clear()
        
        # We could be more selective here, but for simplicity, clear all team averages
        _team_avg_cache = {}
        _team_avg_timestamp = {}
        print(f"Cleared cache for player {player_id} and team averages")
    
    # If a game's data changed
    elif game_id:
        # Clear all caches since game data affects multiple players and team averages
        get_cached_player_base_stats.cache_clear()
        _team_avg_cache = {}
        _team_avg_timestamp = {}
        print(f"Cleared all stats caches due to game {game_id} update")
    
    # If no specific entity changed, clear everything
    else:
        get_cached_player_base_stats.cache_clear()
        _team_avg_cache = {}
        _team_avg_timestamp = {}
        print("Cleared all stats caches")


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
    query = Throw.query.filter_by(
        thrower_id=player.id,
        team_organization_id=get_current_team_id()
    )
    
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
                Throw.created_at > throw.created_at,
                Throw.team_organization_id == get_current_team_id()
            ).order_by(Throw.created_at).first()
            
            if assist:
                hockey_assists += 1
    
    return hockey_assists


def get_player_throw_stats(player, games=None):
    """Get comprehensive throwing statistics for a player"""
    query = Throw.query.filter(
        (Throw.thrower_id == player.id) |
        (Throw.receiver_id == player.id)
    ).filter_by(team_organization_id=get_current_team_id())
    
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
    players = Player.query.filter_by(
        active=True, 
        team=team_name,
        team_organization_id=get_current_team_id()
    ).all()
    
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

PER_WEIGHTS = {
    'scoring': 0.5,
    'assist': 0.5,
    'turnover': -0.75,
    'defense': 0.75,
    'throw': 0.05,
    'plus_minus': 0.1
}

def calculate_per(player, games=None, team_avgs=None):
    """
    Standardized PER calculation with optimizations
    """
    # Use cached stats if possible
    game_ids_tuple = games_to_tuple(games)
    stats = get_cached_player_base_stats(player.id, game_ids_tuple, get_current_team_id())
    
    # Use the optimized function that works with pre-loaded stats
    return calculate_per_from_stats(stats, team_avgs)

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
        lineup_query = LineUp.query.filter_by(
            player_id=player.id,
            team_organization_id=get_current_team_id()
        )
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
        throws_query = Throw.query.filter(
            Throw.thrower_id == player.id,
            Throw.team_organization_id == get_current_team_id()
        )
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
        events_query = Event.query.filter_by(
            player_id=player.id,
            team_organization_id=get_current_team_id()
        )
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
        
        # Initialize plus/minus counters for each line
        stats['o_line_plus_minus'] = 0
        stats['d_line_plus_minus'] = 0
        
        # Get all events for this player
        events_query = Event.query.filter_by(
            player_id=player.id,
            team_organization_id=get_current_team_id()
        )
        if games:
            if isinstance(games, list):
                point_ids = [p.id for g in games for p in g.points]
            else:
                point_ids = [p.id for p in games.points]
            events_query = events_query.filter(Event.point_id.in_(point_ids))
        
        # Define positive and negative event types
        positive_events = ['goal', 'assist', 'block']
        negative_events = ['throwaway', 'drop', 'stall']
        
        # Process all events for this player
        for event in events_query.all():
            # Get the point for this event
            point = Point.query.filter_by(
                id=event.point_id,
                team_organization_id=get_current_team_id()
            ).first()
            
            # Skip if point is None
            if not point:
                continue
                
            # Determine if this is an O-line or D-line point
            is_o_line = point.our_line_type == 'O-line'
            
            # Update plus/minus based on event type
            if event.event_type in positive_events:
                if is_o_line:
                    stats['o_line_plus_minus'] += 1
                else:
                    stats['d_line_plus_minus'] += 1
            elif event.event_type in negative_events:
                if is_o_line:
                    stats['o_line_plus_minus'] -= 1
                else:
                    stats['d_line_plus_minus'] -= 1
        
        # Calculate per point stats
        if stats['o_line_points_played'] > 0:
            stats['o_line_plus_minus_per_point'] = stats['o_line_plus_minus'] / stats['o_line_points_played']
        if stats['d_line_points_played'] > 0:
            stats['d_line_plus_minus_per_point'] = stats['d_line_plus_minus'] / stats['d_line_points_played']

        # Get clips statistics using new relationship pattern
        clips_query = player.clip_appearances.filter_by(
            team_organization_id=get_current_team_id()
        )
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

def process_heatmap_data(team_name=None, player_id=None, opposition_team=None, limit=None, point_ids=None):
    """Process throw data for heatmap visualization with limit and point filtering"""
    heatmap_data = []
    
    # Helper function to add events to heatmap_data
    def add_events_to_heatmap(query, event_type):
        for event in query.all():
            if event.field_position_x is not None and event.field_position_y is not None:
                heatmap_data.append({
                    'x': event.field_position_x,
                    'y': event.field_position_y,
                    'value': 1,
                    'type': event_type
                })

    # 1. Get Throw Start Locations
    throw_query = Throw.query.filter_by(team_organization_id=get_current_team_id())
    if player_id:
        throw_query = throw_query.filter(Throw.thrower_id == player_id)
    if team_name:
        throw_query = throw_query.join(Throw.thrower).filter(Player.team == team_name)
    if point_ids:
        throw_query = throw_query.filter(Throw.point_id.in_(point_ids))
    if limit:
        throw_query = throw_query.limit(limit)
    for throw in throw_query.all():
        if throw.x_start is not None and throw.y_start is not None:
            heatmap_data.append({
                'x': throw.x_start,
                'y': throw.y_start,
                'value': 1,
                'type': 'throw_start'
            })

    # 2. Get Goal, Throwaway, and Scored On Locations from Events
    event_types_to_query = ['goal', 'throwaway', 'scored_on']
    for event_type in event_types_to_query:
        event_query = Event.query.filter_by(
            event_type=event_type,
            team_organization_id=get_current_team_id()
        )
        if player_id:
            event_query = event_query.filter_by(player_id=player_id)
        if team_name:
            event_query = event_query.join(Event.player).filter(Player.team == team_name)
        if point_ids:
            event_query = event_query.filter(Event.point_id.in_(point_ids))
        if limit:
            event_query = event_query.limit(limit)
        
        add_events_to_heatmap(event_query, event_type)

    return heatmap_data



def generate_player_connections(team_name=None, opposition_team=None, min_connections=1, point_ids=None):
    """Generate player connection data using Throws model with minimum connection threshold"""
    query = Throw.query.filter(
        Throw.receiver_id.isnot(None),
        Throw.team_organization_id == get_current_team_id()
    )
    
    if team_name:
        query = query.join(Throw.thrower).filter(Player.team == team_name)
    if opposition_team:
        query = query.filter(Throw.opposition_team == opposition_team)
    if point_ids:
        query = query.filter(Throw.point_id.in_(point_ids))
    
    throws = query.all()
    
    # Rest of the function remains the same...

    
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
    
    # Filter connections by minimum threshold
    if min_connections > 1:
        connections = {k: v for k, v in connections.items() if v['value'] >= min_connections}
    
    # Create nodes list - only include players that have connections after filtering
    player_ids_in_connections = set()
    for conn in connections.values():
        player_ids_in_connections.add(conn['source'])
        player_ids_in_connections.add(conn['target'])
    
    nodes = []
    for player_id in player_ids_in_connections:
        player = Player.query.filter_by(
            id=player_id,
            team_organization_id=get_current_team_id()
        ).first()
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
    Calculate team averages for PER normalization with optimizations
    """
    players = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    ).all()
    
    # Use batch loading for player stats
    player_stats = get_players_base_stats(players, games)
    
    totals = {
        'o_line_plus_minus': 0,
        'o_line_points': 0,
        'd_line_plus_minus': 0,
        'd_line_points': 0,
        'uper_total': 0,
        'player_count': 0
    }

    # First pass to calculate basic averages
    for player_id, stats in player_stats.items():
        if stats['points_played'] > 0:
            totals['player_count'] += 1
            totals['o_line_plus_minus'] += stats.get('o_line_plus_minus', 0)
            totals['o_line_points'] += stats.get('o_line_points_played', 0)
            totals['d_line_plus_minus'] += stats.get('d_line_plus_minus', 0)
            totals['d_line_points'] += stats.get('d_line_points_played', 0)
    
    # Calculate initial averages
    initial_avgs = {
        'avg_o_line_plus_minus_per_point': (totals['o_line_plus_minus'] / totals['o_line_points']) if totals['o_line_points'] > 0 else 0,
        'avg_d_line_plus_minus_per_point': (totals['d_line_plus_minus'] / totals['d_line_points']) if totals['d_line_points'] > 0 else 0,
        'avg_uper': 1  # Initial placeholder
    }
    
    # Second pass to calculate uPER using the initial averages
    for player_id, stats in player_stats.items():
        if stats['points_played'] > 0:
            # Calculate unadjusted PER without the plus-minus component
            # since we don't have the final team averages yet
            raw_uper = calculate_unadjusted_per(stats)
            totals['uper_total'] += raw_uper
    
    # Update with final avg_uper
    initial_avgs['avg_uper'] = totals['uper_total'] / totals['player_count'] if totals['player_count'] > 0 else 1
    
    return initial_avgs

def calculate_game_stats(game):
    """
    Calculate comprehensive game statistics
    """
    # Safely get points
    try:
        if hasattr(game.points, 'all'):
            all_points = game.points.all()
        else:
            all_points = game.points
            
        if hasattr(game.o_line_points, 'all'):
            o_points = game.o_line_points.all()
        else:
            o_points = game.o_line_points
            
        if hasattr(game.d_line_points, 'all'):
            d_points = game.d_line_points.all()
        else:
            d_points = game.d_line_points
    except Exception as e:
        print(f"Error getting points for game {game.id}: {str(e)}")
        all_points = []
        o_points = []
        d_points = []
    
    stats = {
        'o_line_points': len(o_points),
        'o_line_conversions': sum(1 for p in o_points if p.we_scored),
        'd_line_points': len(d_points),
        'd_line_conversions': sum(1 for p in d_points if p.we_scored),
        'breaks': sum(1 for p in all_points if p.is_break),
        'holds': sum(1 for p in all_points if p.is_hold),
        'turnovers': 0,
        'possessions': 0,
        'point_flow': []
    }

    
    # Calculate conversion rates
    stats['o_line_conversion_rate'] = (stats['o_line_conversions'] / stats['o_line_points'] * 100) if stats['o_line_points'] > 0 else 0
    stats['d_line_conversion_rate'] = (stats['d_line_conversions'] / stats['d_line_points'] * 100) if stats['d_line_points'] > 0 else 0
    
    # Calculate point flow data
    for point in sorted(all_points, key=lambda p: p.point_number):
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
        point_events = Event.query.filter_by(
            point_id=point.id,
            team_organization_id=get_current_team_id()
        ).order_by(Event.timestamp).all()
        
        stats['turnovers'] += sum(1 for e in point_events if e.event_type in ['throwaway', 'drop', 'stall'])
        stats['possessions'] += count_possessions(point_events)
    
    return stats

# --- Routes ---

@bp.route('/debug/throws')
@login_required
def debug_throws():
    """Debug view for throws model"""
    throws = Throw.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(Throw.created_at.desc()).limit(100).all()
    
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
        'connection_data': {'nodes': [], 'links': []},
        'team_avg_stats': {}
    }

    try:
        # Get team name from current user's player
        team_name = None
        if hasattr(current_user, 'player') and current_user.player:
            team_name = current_user.player.team

        # Get active players with eager loading
        players_query = Player.query.filter_by(
            active=True,
            team_organization_id=get_current_team_id()
        )
        if team_name:
            players_query = players_query.filter_by(team=team_name)
        players = players_query.all()

        if not players:
            flash("No active players found", "warning")
            return render_template('stats/index.html', **default_context)


        # Get recent games with eager loading for tournament only
        recent_games = Game.query.filter_by(
            team_organization_id=get_current_team_id()
        ).options(
            db.joinedload(Game.tournament)
        ).order_by(Game.date.desc()).all()
        
        # For each game, explicitly load points to handle dynamic relationship
        for game in recent_games:
            # Force loading of points
            if hasattr(game.points, 'all'):
                _ = game.points.all()


        
        if not recent_games:
            return render_template('stats/index.html', **default_context)

        # Start timing the expensive operations
        import time
        start_time = time.time()
        
        # Calculate team summary stats - SAME AS TEAM_STATS ROUTE
        team_summary = calculate_team_summary(recent_games)
        
        # Add additional metrics for radar charts - SAME AS TEAM_STATS ROUTE
        team_summary.update(calculate_additional_team_metrics(recent_games))
        
        # Calculate previous period stats for comparison - SAME AS TEAM_STATS ROUTE
        # For index, we don't have filters, so we'll get previous games based on dates
        prev_games = recent_games[1:] if len(recent_games) > 1 else []
        prev_summary = calculate_team_summary(prev_games)
        prev_metrics = calculate_additional_team_metrics(prev_games)
        
        # Add previous metrics with 'prev_' prefix - SAME AS TEAM_STATS ROUTE
        for key, value in prev_metrics.items():
            team_summary[f'prev_{key}'] = value
        for key, value in prev_summary.items():
            if key not in team_summary:
                team_summary[f'prev_{key}'] = value
        
        # Calculate game stats
        team_stats = []
        for game in recent_games[:5]:  # Limit to most recent 5 games for performance
            try:
                stats = calculate_game_stats(game)
                team_stats.append({'stats': stats})
            except Exception as e:
                print(f"Error calculating stats for game {game.id}: {str(e)}")
                continue
                
        # Calculate team averages once for all players
        print("Calculating team averages...")
        team_avgs = get_cached_team_averages(recent_games)
        
        # Calculate player stats in batch
        print("Calculating player stats in batch...")
        player_stats = get_players_base_stats(players, recent_games)
        
        # Calculate PER for each player using the preloaded stats
        print("Calculating PER for each player...")
        for player_id, stats in player_stats.items():
            if stats['points_played'] > 0:
                stats['per'] = calculate_per_from_stats(stats, team_avgs)

        
        print(f"Stats calculation took {time.time() - start_time:.2f} seconds")
        
        # Determine O-line and D-line players based on point participation
        # This part is already optimized by using the preloaded player stats
        o_line_candidates = []
        d_line_candidates = []

        for player in players:
            if player.id in player_stats:
                stats = player_stats[player.id]
                o_line_points = stats.get('o_line_points_played', 0)
                d_line_points = stats.get('d_line_points_played', 0)
                
                if o_line_points > 0:
                    o_line_candidates.append(player)
                if d_line_points > 0:
                    d_line_candidates.append(player)

        # Calculate line efficiency with gender separation
        # This function should be optimized to use the preloaded player stats
        o_line_efficiency = calculate_optimized_line_efficiency(o_line_candidates, player_stats, is_offensive=True)
        d_line_efficiency = calculate_optimized_line_efficiency(d_line_candidates, player_stats, is_offensive=False)
        
        # Separate players by gender with fallback
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
        
        # Calculate team average stats
        team_avg_stats = calculate_team_avg_stats(player_stats)
        
        # Generate heatmap and connection data
        # Consider limiting the amount of data processed here
        heatmap_data = process_heatmap_data(team_name=team_name, limit=1000)  # Limit to 1000 data points
        connection_data = generate_player_connections(team_name=team_name, min_connections=2)  # Only include connections with at least 2 throws

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
            connection_data=json.dumps(connection_data),
            team_avg_stats=team_avg_stats,
            is_admin=is_admin(current_user),
            is_coach=is_coach(current_user)
        )

    except Exception as e:
        print(f"Error in index route: {str(e)}")
        import traceback
        traceback.print_exc()
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
            'labels': [],
            'o_line_efficiency': [],
            'd_line_efficiency': [],
            'break_percentage': []
        }
    
    # Filter out games with no points
    games_with_points = []
    for game in games:
        try:
            # If game.points is a query object
            points = game.points.all()
            if len(points) > 0:
                games_with_points.append(game)
        except AttributeError:
            # If game.points is already a list
            if len(game.points) > 0:
                games_with_points.append(game)
    
    # If no games with points, return empty data
    if not games_with_points:
        return {
            'dates': [],
            'labels': [],
            'o_line_efficiency': [],
            'd_line_efficiency': [],
            'break_percentage': []
        }
    
    # Sort games by date using string representation (safest approach)
    sorted_games = sorted(games_with_points, key=lambda g: str(g.date) if g.date else "")
    
    # Calculate metrics for each game
    dates = []
    labels = []
    o_line_efficiency = []
    d_line_efficiency = []
    break_percentage = []
    
    for game in sorted_games:
        # Add date for sorting purposes
        if game.date:
            dates.append(game.date.strftime('%Y-%m-%d') if hasattr(game.date, 'strftime') else str(game.date))
        else:
            dates.append('Unknown')
        
        # Create custom label with opposition and tournament name
        # Use game.opponent instead of game.opposition_team
        opposition_name = game.opponent if hasattr(game, 'opponent') and game.opponent else "Unknown"
        tournament_name = game.tournament.name if hasattr(game, 'tournament') and game.tournament else "Unknown"
        custom_label = f"{opposition_name} ({tournament_name})"
        labels.append(custom_label)

        
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
        'labels': json.dumps(labels),
        'o_line_efficiency': json.dumps(o_line_efficiency),
        'd_line_efficiency': json.dumps(d_line_efficiency),
        'break_percentage': json.dumps(break_percentage)
    }

@bp.route('/player/<int:player_id>')
@login_required
def player_stats(player_id):
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Check if user has permission to view this player's stats
    if not (is_admin(current_user) or is_coach(current_user) or (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player.id)):
        flash("You don't have permission to view this player's statistics", "danger")
        return redirect(url_for('stats_dashboard.index'))
    
    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    game_id = request.args.get('game_id', type=int)

    # Determine which games to analyze
    if game_id:
        games = [Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first()] if Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first() else []
    elif tournament_id:
        tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first()
        games = tournament.games.filter_by(
            team_organization_id=get_current_team_id()
        ).all() if tournament else []
    else:
        games = Game.query.filter_by(
            team_organization_id=get_current_team_id()
        ).all()
    
    # Use the new batch function for a single player to ensure consistency
    player_stats_dict = get_players_base_stats([player], games)
    stats = player_stats_dict[player.id]
    
    # Calculate team averages specifically for these games
    team_avgs = get_cached_team_averages(games)
    
    if stats['points_played'] > 0:
        stats['per'] = calculate_per_from_stats(stats, team_avgs)
    
    # Add hucks to player stats
    stats['hucks'] = sum(1 for t in stats['throw_vectors'] if t['distance'] > 20)
    
    # Get point IDs for filtering if games are selected
    point_ids = get_point_ids_from_games(games)

    # --- Team-level summary calculations ---
    team_summary = calculate_team_summary(games)
    team_summary.update(calculate_additional_team_metrics(games))

    # --- Cutting Skills Calculations ---
    cutting_skills_query = CuttingSkill.query.filter_by(
        player_id=player_id,
        team_organization_id=get_current_team_id()
    )
    if point_ids:
        cutting_skills_query = cutting_skills_query.filter(CuttingSkill.point_id.in_(point_ids))
    cutting_skills = cutting_skills_query.all()
    cutting_data = [skill.to_dict() for skill in cutting_skills]
    cutting_stats = calculate_cutting_stats(cutting_skills) # Refactored for clarity

    # --- Game History Calculation ---
    player_games = get_player_game_history(player, tournament_id, game_id)

    # --- Turnover Analysis ---
    most_common_throwaway_location = calculate_most_common_throwaway_location(player, games)
    throwaway_direction_data = calculate_most_common_throwaway_direction(player, games)
    if throwaway_direction_data and throwaway_direction_data.get('total', 0) > 0:
        throwaway_direction_data['percentage'] = (throwaway_direction_data['count'] / throwaway_direction_data['total']) * 100
    else:
        throwaway_direction_data['percentage'] = 0

    # --- CORRECTED AND CONSOLIDATED RADAR CHART METRICS ---
    # This block ensures all necessary stats are calculated and correctly formatted.
    if stats['points_played'] > 0:
        # Offensive metrics
        stats['goals_per_point'] = stats['goals'] / stats['points_played']
        stats['assists_per_point'] = stats['assists'] / stats['points_played']
        stats['throws_per_point'] = stats['throws'] / stats['points_played']
        stats['hucks_per_point'] = stats.get('hucks', 0) / stats['points_played']
        
        # Defensive metrics
        if stats['d_line_points_played'] > 0:
            stats['blocks_per_point'] = stats['blocks'] / stats['d_line_points_played']
            stats['turnovers_forced_per_point'] = (stats['blocks'] + stats.get('stalls', 0)) / stats['d_line_points_played']
        else:
            stats['blocks_per_point'] = 0
            stats['turnovers_forced_per_point'] = 0
            
        # O-Line Conversion Rate Calculation
        if stats['o_line_points_played'] > 0:
            o_line_points_player_was_in = db.session.query(Point).join(LineUp).filter(
                LineUp.player_id == player.id, 
                Point.our_line_type == 'O-line',
                Point.id.in_(point_ids)
            )
            o_line_scores = o_line_points_player_was_in.filter(Point.we_scored == True).count()
            stats['o_line_conversion_rate'] = (o_line_scores / stats['o_line_points_played']) * 100
        else:
            stats['o_line_conversion_rate'] = 0

        # --- OPTIMIZED D-LINE CONVERSION CALCULATION ---
        # Get the count of D-line points the player participated in
        d_line_points_query = db.session.query(Point).join(
            Event, Point.id == Event.point_id
        ).filter(
            Point.our_line_type == 'D-line',
            Event.player_id == player.id,
            Point.game_id.in_([g.id for g in games]),
            Point.team_organization_id == get_current_team_id()
        ).distinct(Point.id)
        
        # Count total points and scored points
        d_line_points_played = 0
        d_line_points_scored = 0
        
        for point in d_line_points_query:
            d_line_points_played += 1
            if point.we_scored:
                d_line_points_scored += 1
        
        # Calculate D-line conversion rate
        if d_line_points_played > 0:
            stats['d_line_conversion_rate'] = (d_line_points_scored / d_line_points_played) * 100
            # Log for debugging
            print(f"DEBUG: Player {player.name} - D-line points played: {d_line_points_played}, scored: {d_line_points_scored}, rate: {stats['d_line_conversion_rate']}%")
        else:
            stats['d_line_conversion_rate'] = 0
        
        # This also serves as the Defensive Efficiency for the player
        stats['defensive_efficiency'] = stats['d_line_conversion_rate']
    else:
        # Default all per-point metrics to 0 if no points played
        stats['goals_per_point'] = 0
        stats['assists_per_point'] = 0
        stats['throws_per_point'] = 0
        stats['hucks_per_point'] = 0
        stats['blocks_per_point'] = 0
        stats['turnovers_forced_per_point'] = 0
        stats['o_line_conversion_rate'] = 0
        stats['d_line_conversion_rate'] = 0

    # Ensure team_summary has defensive_efficiency for comparison
    if 'defensive_efficiency' not in team_summary:
        team_summary['defensive_efficiency'] = team_summary.get('d_line_conversion_rate', 0)

    tournaments = Tournament.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(Tournament.start_date.desc()).all()

    # Add this right after calculating d_line_conversion_rate
    print(f"DEBUG: Player {player.name}")
    print(f"DEBUG: d_line_points_played = {stats['d_line_points_played']}")
    print(f"DEBUG: d_line_conversion_rate = {stats['d_line_conversion_rate']}")
    
    # Also print the point IDs to check if they match what we expect
    point_ids_list = [p_id for p_id in point_ids] if point_ids else []
    print(f"DEBUG: point_ids = {point_ids_list}")

    return render_template(
        'stats/player_stats.html',
        player=player,
        stats=stats,
        team_summary=team_summary, 
        player_games=player_games,
        tournaments=tournaments,
        selected_tournament=tournament_id,
        selected_game=game_id,
        throw_vectors=stats['throw_vectors'],
        throwaway_locations=[],
        throw_stats={
            'total_throws': stats['throws'],
            'completions': stats['completions'],
            'assists': stats['assists'],
            'hockey_assists': stats['hockey_assists'],
            'average_distance': stats['avg_throw_distance']
        },
        total_throw_distance=stats['total_throw_distance'],
        avg_throw_distance=stats['avg_throw_distance'],
        throw_directions=stats['throw_directions'],
        completion_by_direction=stats['completion_by_direction'],
        cutting_data=cutting_data,
        cutting_stats=cutting_stats,
        most_common_throwaway_location=most_common_throwaway_location,
        throwaway_direction_data=throwaway_direction_data
    )

# You will also need to add these two new helper functions to stats.py
# (or refactor the existing code into them)

def calculate_cutting_stats(cutting_skills):
    """Processes a list of cutting skills and returns a summary dictionary."""
    stats = {
        'total_cuts': len(cutting_skills),
        'total_open_looked_off': sum(1 for s in cutting_skills if s.outcome == 'open_looked_off'),
        'total_guarded_looked_off': sum(1 for s in cutting_skills if s.outcome == 'guarded_looked_off'),
        'total_open_thrown_to': sum(1 for s in cutting_skills if s.outcome == 'open_thrown_to'),
        'total_guarded_thrown_to': sum(1 for s in cutting_skills if s.outcome == 'guarded_thrown_to'),
        'by_type': {},
        'success_rate': 0,
        'open_rate': 0,
        'preferred_cut': 'N/A'
    }
    
    successful_cuts = stats['total_open_thrown_to'] + stats['total_guarded_thrown_to']
    if stats['total_cuts'] > 0:
        stats['success_rate'] = (successful_cuts / stats['total_cuts']) * 100
        open_cuts = stats['total_open_looked_off'] + stats['total_open_thrown_to']
        stats['open_rate'] = (open_cuts / stats['total_cuts']) * 100

    cut_types = ['open_deep', 'open_under', 'break_deep', 'break_under']
    for cut_type in cut_types:
        type_skills = [s for s in cutting_skills if s.cutting_type == cut_type]
        total = len(type_skills)
        open_thrown_to = sum(1 for s in type_skills if s.outcome == 'open_thrown_to')
        guarded_thrown_to = sum(1 for s in type_skills if s.outcome == 'guarded_thrown_to')
        
        stats['by_type'][cut_type] = {
            'total': total,
            'open_looked_off': sum(1 for s in type_skills if s.outcome == 'open_looked_off'),
            'guarded_looked_off': sum(1 for s in type_skills if s.outcome == 'guarded_looked_off'),
            'open_thrown_to': open_thrown_to,
            'guarded_thrown_to': guarded_thrown_to,
            'success_rate': ((open_thrown_to + guarded_thrown_to) / total) * 100 if total > 0 else 0
        }

    if stats['total_cuts'] > 0:
        preferred_cut_type = max(cut_types, key=lambda ct: stats['by_type'][ct]['total'] if ct in stats['by_type'] else 0)
        if stats['by_type'].get(preferred_cut_type, {}).get('total', 0) > 0:
            stats['preferred_cut'] = preferred_cut_type.replace('_', ' ').title()
            
    return stats

def get_player_game_history(player, tournament_id, game_id):
    """Fetches and calculates stats for a player's game history."""
    player_games = []
    games_query = Game.query.filter_by(team_organization_id=get_current_team_id())
    if tournament_id:
        games_query = games_query.filter_by(tournament_id=tournament_id)
    elif game_id:
        games_query = games_query.filter_by(id=game_id)
    
    for game in games_query.order_by(Game.date.desc()).all():
        if LineUp.query.join(Point).filter(LineUp.player_id == player.id, Point.game_id == game.id).first():
            game_stats_dict = get_players_base_stats([player], [game])
            game_stats = game_stats_dict[player.id]
            game_team_avgs = get_cached_team_averages([game])
            game_stats['per'] = calculate_per_from_stats(game_stats, game_team_avgs)
            player_games.append({'game': game, 'stats': game_stats})
            
    return player_games


@bp.route('/game/<int:game_id>')
@login_required
def game_stats(game_id):
    """
    Comprehensive game statistics and visualizations
    """
    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Calculate team statistics
    team_stats = calculate_game_stats(game)
    
    # Get all players who participated in this game
    player_ids = db.session.query(LineUp.player_id).join(Point).filter(
        Point.game_id == game_id,
        LineUp.team_organization_id == get_current_team_id(),
        Point.team_organization_id == get_current_team_id()
    ).distinct().all()
    
    player_ids = [pid[0] for pid in player_ids]
    players = Player.query.filter(
        Player.id.in_(player_ids),
        Player.team_organization_id == get_current_team_id()
    ).all()
    
    # Calculate team averages for this game
    team_avgs = get_cached_team_averages([game])
    
    # Get player stats in batch
    player_stats_dict = get_players_base_stats(players, [game])
    
    # Format player stats for template
    player_stats = []
    for player in players:
        if player.id in player_stats_dict:
            stats = player_stats_dict[player.id]
            stats['per'] = calculate_per(player, [game], team_avgs)
            player_stats.append({
                'player': player,
                'stats': stats
            })
    
    # Sort by points played
    player_stats.sort(key=lambda x: x['stats']['points_played'], reverse=True)
    
    # Get team name from the first player (assuming all players are on the same team)
    team_name = None
    if players:
        first_player = players[0]
        team_name = first_player.team
    
    # Generate visualization data
    point_ids = [p.id for p in game.points]
    heatmap_data = process_heatmap_data(team_name=team_name, point_ids=point_ids)
    connection_data = generate_player_connections(team_name=team_name, min_connections=2, point_ids=point_ids)
    
    # Add additional team metrics
    team_stats.update(calculate_additional_team_metrics([game]))
    
    return render_template(
        'stats/game_stats.html',
        game=game,
        team_stats=team_stats,
        player_stats=player_stats,
        heatmap_data=json.dumps(heatmap_data),
        connections=json.dumps(connection_data),
        calculate_impact_score=calculate_impact_score,
        is_admin=is_admin,
        is_coach=is_coach
    )


def calculate_impact_score(stats):
    """Calculate impact score for a player"""
    # Your impact score calculation logic here
    # For example:
    return (stats['goals'] * 2 + stats['assists'] * 1.5 + 
            stats['blocks'] * 1.5 - stats['turnovers'])

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
    games_query = Game.query.filter_by(team_organization_id=get_current_team_id())
    if tournament_id:
        games_query = games_query.filter_by(tournament_id=tournament_id)
    elif season:
        tournament_ids = [t.id for t in Tournament.query.filter_by(
            season=season,
            team_organization_id=get_current_team_id()
        ).all()]
        games_query = games_query.filter(Game.tournament_id.in_(tournament_ids))
    
    # Use eager loading for related data
    # Use eager loading for tournament only
    games_query = games_query.options(
        db.joinedload(Game.tournament)
    )
    
    games = games_query.order_by(Game.date).all()
    
    # For each game, explicitly load points to handle dynamic relationship
    for game in games:
        # Force loading of points
        if hasattr(game.points, 'all'):
            _ = game.points.all()

    
  
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
    
    # Get team name from current user's player
    team_name = None
    if hasattr(current_user, 'player') and current_user.player:
        team_name = current_user.player.team
    
    # Calculate player statistics
    players_query = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    )
    if team_name:
        players_query = players_query.filter_by(team=team_name)
    players = players_query.all()
    
    # Get cached team averages
    team_avgs = get_cached_team_averages(games)
    
    # Get player stats in batch
    player_stats_dict = get_players_base_stats(players, games)
    
    # Format player stats for template
    player_stats = []
    for player in players:
        if player.id in player_stats_dict:
            stats = player_stats_dict[player.id]
            if stats['points_played'] > 0:
                stats['per'] = calculate_per(player, games, team_avgs)
                player_stats.append({
                    'player': player,
                    'stats': stats
                })
    
    # Sort by PER
    player_stats.sort(key=lambda x: x['stats']['per'], reverse=True)
    
    # Calculate line efficiency with gender separation
    o_line_candidates = [p for p in players if player_stats_dict.get(p.id, {}).get('o_line_points_played', 0) > 0]
    d_line_candidates = [p for p in players if player_stats_dict.get(p.id, {}).get('d_line_points_played', 0) > 0]
    
    o_line_efficiency = calculate_optimized_line_efficiency(o_line_candidates, player_stats_dict, is_offensive=True)
    d_line_efficiency = calculate_optimized_line_efficiency(d_line_candidates, player_stats_dict, is_offensive=False)
    
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
    tournaments = Tournament.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(Tournament.start_date.desc()).all()
    
    seasons = db.session.query(Tournament.season).filter_by(
        team_organization_id=get_current_team_id()
    ).distinct().all()
    seasons = [s[0] for s in seasons if s[0]]
    
    return render_template(
        'stats/team_stats.html',
        player_stats=player_stats_dict,
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
        Event.event_type.in_(['catch', 'goal']),
        Event.team_organization_id == get_current_team_id()
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
            previous_catch = Event.query.filter_by(
                id=event.previous_catch_id,
                team_organization_id=get_current_team_id()
            ).first()
            
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
    events_query = Event.query.filter_by(
        player_id=player.id, 
        event_type='throwaway',
        team_organization_id=get_current_team_id()
    )
    
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
                Event.timestamp < event.timestamp,
                Event.team_organization_id == get_current_team_id()
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
    query = LineUp.query.filter_by(
        player_id=player.id,
        team_organization_id=get_current_team_id()
    )
    
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
        query = LineUp.query.filter_by(
            player_id=player.id,
            team_organization_id=get_current_team_id()
        ).join(Point)
        
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
        'total_points': 0,
        'o_line_points': 0,
        'o_line_conversions': 0,
        'd_line_points': 0,
        'd_line_conversions': 0,
        'breaks': 0,
        'holds': 0
    }
    
    # Safely count total points
    for game in games:
        try:
            if hasattr(game.points, 'all'):
                points = game.points.all()
            else:
                points = game.points
            summary['total_points'] += len(points)
        except Exception as e:
            print(f"Error counting points for game {game.id}: {str(e)}")


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
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    point_stats = PlayerPointStats.query.filter_by(
        player_id=player_id,
        team_organization_id=get_current_team_id()
    ).all()
    
    events = Event.query.filter_by(
        player_id=player_id,
        team_organization_id=get_current_team_id()
    ).all()
    
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
    # We can use the throw vectors from the player stats
    if not games:
        return 0
        
    # Use the throw vectors from player stats
    player_stats_dict = get_players_base_stats([player], games)
    if player.id not in player_stats_dict:
        return 0
        
    stats = player_stats_dict[player.id]
    return sum(1 for t in stats['throw_vectors'] if t['distance'] > 20)



@bp.route('/debug/players')
@login_required
def debug_players():
    players = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    ).all()
    
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
    break_throws = Throw.query.filter_by(
        break_throw=True,
        team_organization_id=get_current_team_id()
    ).all()
    
    # Get total throws for comparison
    total_throws = Throw.query.filter_by(
        team_organization_id=get_current_team_id()
    ).count()
    
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
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    game_id = request.args.get('game_id', type=int)

    # Determine which games to analyze
    if game_id:
        games = [Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first()] if Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first() else []
    elif tournament_id:
        tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first()
        games = tournament.games.filter_by(
            team_organization_id=get_current_team_id()
        ).all() if tournament else []
    else:
        games = Game.query.filter_by(
            team_organization_id=get_current_team_id()
        ).all()
    
    # Get player stats
    stats = get_player_base_stats(player, games)
    
    # Calculate team averages
    team_avgs = calculate_team_averages(games)
    
    # Calculate raw PER values for all players to find max
    all_players = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    ).all()
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
        goals_component = WEIGHTS['scoring'] * (stats['goals'] * 0.75)
        assists_component = WEIGHTS['assist'] * (stats['assists'] * 0.75)
        hockey_assists_component = WEIGHTS['assist'] * 0.5 * (stats['hockey_assists'] * 0.75)
        turnovers_component = WEIGHTS['turnover'] * ((stats['throwaways'] + stats['drops']) * 0.75)
        blocks_component = WEIGHTS['defense'] * (stats['blocks'] * 0.75)
        stalls_component = WEIGHTS['defense'] * (-1) * (stats.get('stalls', 0) * 0.75)
        callahans_component = 1.0 * (stats.get('callahans', 0) * 0.75)
        
        box_component = goals_component + assists_component + hockey_assists_component + turnovers_component + blocks_component + stalls_component + callahans_component
        
        # Passing component calculations
        completion_factor = (stats['completion_rate']/100) * 3.0
        catch_factor = (stats['catch_rate']/100) * 3.0
        completions_component = (stats['completions'] * 0.75) * completion_factor
        catches_component = (stats['catches'] * 0.75) * catch_factor
        passing_component = WEIGHTS['throw'] * (completions_component + catches_component)
        
        # Get number of points played in each line
        o_line_points = stats.get('o_line_points_played', 0)
        d_line_points = stats.get('d_line_points_played', 0)
        total_points = o_line_points + d_line_points
        
        # Calculate weighted plus-minus component
        if total_points > 0:
            o_line_weight = o_line_points / total_points if o_line_points > 0 else 0
            d_line_weight = d_line_points / total_points if d_line_points > 0 else 0
            
            # Use the variable names expected by the template
            o_line = o_line_weight * (stats.get('o_line_plus_minus_per_point', 0) - team_avgs.get('avg_o_line_plus_minus_per_point', 0))
            d_line = d_line_weight * (stats.get('d_line_plus_minus_per_point', 0) - team_avgs.get('avg_d_line_plus_minus_per_point', 0))
            
            plus_minus_component = WEIGHTS['plus_minus'] * (o_line + d_line)
        else:
            o_line_weight = 0
            d_line_weight = 0
            o_line = 0
            d_line = 0
            plus_minus_component = 0
        
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
                'o_line_points_played': o_line_points,
                'd_line_points_played': d_line_points,
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
                'o_line_points': o_line_points,
                'd_line_points': d_line_points,
                'o_line_weight': o_line_weight,
                'd_line_weight': d_line_weight,
                'o_line': o_line,  # Match the template variable name
                'd_line': d_line,  # Match the template variable name
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
    tournaments = Tournament.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(Tournament.start_date.desc()).all()
    
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
    
    # Count total points
    total_points = 0
    for game in games:
        try:
            points = game.points.all() if hasattr(game.points, 'all') else game.points
            total_points += len(points)
        except Exception as e:
            print(f"Error counting points for game {game.id}: {str(e)}")
    
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
            points = game.points.all() if hasattr(game.points, 'all') else game.points
            point_ids.extend([p.id for p in points])
        except Exception as e:
            print(f"Error getting points for game {game.id}: {str(e)}")
    
    # Count all throws
    throws_query = Throw.query.filter_by(team_organization_id=get_current_team_id())
    throws_query = throws_query.filter(Throw.point_id.in_(point_ids))
    throws = throws_query.all()
    
    # Count completions
    completions = sum(1 for t in throws if t.is_completion)
    
    # Count goals and assists
    goals = sum(1 for t in throws if t.throw_type == 'assist')
    
    # Count blocks
    blocks_query = Event.query.filter_by(
        event_type='block',
        team_organization_id=get_current_team_id()
    )
    blocks_query = blocks_query.filter(Event.point_id.in_(point_ids))
    blocks = blocks_query.count()
    
    # Count turnovers forced
    turnovers_forced_query = Event.query.filter(
        Event.event_type.in_(['throwaway', 'drop', 'stall']),
        Event.is_offensive == False,
        Event.team_organization_id == get_current_team_id()
    )
    turnovers_forced_query = turnovers_forced_query.filter(Event.point_id.in_(point_ids))
    turnovers_forced = turnovers_forced_query.count() + blocks
    
    # Count hucks
    hucks = sum(1 for t in throws if t.calculate_distance() and t.calculate_distance() > 20)
    
    # Calculate break percentage
    breaks = 0
    for game in games:
        try:
            points = game.points.all() if hasattr(game.points, 'all') else game.points
            breaks += sum(1 for p in points if p.is_break)
        except Exception as e:
            print(f"Error calculating breaks for game {game.id}: {str(e)}")
    break_percentage = (breaks / total_points) * 100 if total_points > 0 else 0
    
    # Calculate defensive efficiency
    d_points_count = 0
    d_conversions = 0
    for game in games:
        try:
            d_points = game.d_line_points.all() if hasattr(game.d_line_points, 'all') else game.d_line_points
            d_points_count += len(d_points)
            d_conversions += sum(1 for p in d_points if p.we_scored)
        except Exception as e:
            print(f"Error calculating d-line stats for game {game.id}: {str(e)}")
    defensive_efficiency = (d_conversions / d_points_count) * 100 if d_points_count > 0 else 0
    
    # Calculate o-line points
    o_points_count = 0
    for game in games:
        try:
            o_points = game.o_line_points.all() if hasattr(game.o_line_points, 'all') else game.o_line_points
            o_points_count += len(o_points)
        except Exception as e:
            print(f"Error calculating o-line stats for game {game.id}: {str(e)}")
    
    # Calculate throws per point correctly - total throws divided by total points
    throws_per_point = len(throws) / total_points if total_points > 0 else 0
    
    result = {
        'completion_rate': (completions / len(throws)) * 100 if throws else 0,
        'goals_per_point': goals / total_points,
        'assists_per_point': goals / total_points,  # Same as goals
        'throws_per_point': throws_per_point,
        'hucks_per_point': hucks / total_points,
        'blocks_per_point': blocks / total_points,
        'turnovers_forced_per_point': turnovers_forced / total_points,
        'defensive_efficiency': defensive_efficiency,
        'break_percentage': break_percentage
    }
    
    return result


def count_d_line_possessions(point):
    """Count number of D-line possessions in a point"""
    possessions = 0
    has_possession = False
    
    # Sort events by timestamp
    events = sorted(point.events, key=lambda e: e.timestamp or 0)
    
    for event in events:
        # D-line gains possession through a block
        if event.event_type == 'block' and not has_possession:
            has_possession = True
            possessions += 1
        
        # D-line scores (end of possession)
        elif event.event_type == 'goal' and has_possession:
            has_possession = False
        
        # D-line turns it over (end of possession)
        elif event.event_type in ['throwaway', 'drop', 'stall'] and has_possession:
            has_possession = False
    
    return possessions

def get_previous_period_games(season, tournament_id):
    """Get games from previous period for comparison"""
    if tournament_id:
        # Get current tournament
        current_tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first()
        
        if current_tournament:
            # Find previous tournament in same season
            prev_tournament = Tournament.query.filter(
                Tournament.season == current_tournament.season,
                Tournament.start_date < current_tournament.start_date,
                Tournament.team_organization_id == get_current_team_id()
            ).order_by(Tournament.start_date.desc()).first()
            
            if prev_tournament:
                return Game.query.filter_by(
                    tournament_id=prev_tournament.id,
                    team_organization_id=get_current_team_id()
                ).all()
    elif season:
        # Get previous season
        seasons = db.session.query(Tournament.season).filter_by(
            team_organization_id=get_current_team_id()
        ).distinct().order_by(Tournament.season).all()
        
        seasons = [s[0] for s in seasons if s[0]]
        
        if season in seasons:
            idx = seasons.index(season)
            if idx > 0:
                prev_season = seasons[idx - 1]
                tournament_ids = [t.id for t in Tournament.query.filter_by(
                    season=prev_season,
                    team_organization_id=get_current_team_id()
                ).all()]
                
                return Game.query.filter(
                    Game.tournament_id.in_(tournament_ids),
                    Game.team_organization_id == get_current_team_id()
                ).all()
    
    # Default: return empty list if no previous period found
    return []

@bp.route('/debug/line_plus_minus/<int:player_id>')
@login_required
def debug_line_plus_minus(player_id):
    """Debug view for O-line and D-line plus/minus calculation"""
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    game_id = request.args.get('game_id', type=int)

    # Determine which games to analyze
    if game_id:
        games = [Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first()] if Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first() else []
    elif tournament_id:
        tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first()
        games = tournament.games.filter_by(
            team_organization_id=get_current_team_id()
        ).all() if tournament else []
    else:
        games = Game.query.filter_by(
            team_organization_id=get_current_team_id()
        ).all()
    
    # Get points played by this player
    lineup_query = LineUp.query.filter_by(
        player_id=player.id,
        team_organization_id=get_current_team_id()
    )
    if games:
        if isinstance(games, list):
            point_ids = [p.id for g in games for p in g.points]
        else:
            point_ids = [p.id for p in games.points]
        lineup_query = lineup_query.filter(LineUp.point_id.in_(point_ids))
    
    points_played = lineup_query.all()
    
    # Separate into O-line and D-line points
    o_line_points = [p for p in points_played if p.point.our_line_type == 'O-line']
    d_line_points = [p for p in points_played if p.point.our_line_type == 'D-line']
    
    # Initialize debug data structures
    o_line_events = []
    d_line_events = []
    o_line_plus_minus = 0
    d_line_plus_minus = 0
    
    # Define positive and negative event types
    positive_events = ['goal', 'assist', 'block']
    negative_events = ['throwaway', 'drop', 'stall']
    
    # Get all events for this player
    events_query = Event.query.filter_by(
        player_id=player.id,
        team_organization_id=get_current_team_id()
    )
    if games:
        if isinstance(games, list):
            point_ids = [p.id for g in games for p in g.points]
        else:
            point_ids = [p.id for p in games.points]
        events_query = events_query.filter(Event.point_id.in_(point_ids))
    
    # Process all events for this player
    for event in events_query.order_by(Event.timestamp).all():
        # Get the point for this event
        point = Point.query.filter_by(
            id=event.point_id,
            team_organization_id=get_current_team_id()
        ).first()
        
        # Skip if point is None
        if not point:
            continue
            
        # Create event data for display
        event_data = {
            'point_id': point.id,
            'game_id': point.game_id,
            'game_description': f"Game #{point.game_id}" if point.game_id else "Unknown",
            'game_date': point.game.date.strftime('%Y-%m-%d') if point.game and hasattr(point.game, 'date') and point.game.date else "Unknown",
            'event_type': event.event_type,
            'timestamp': event.timestamp.strftime('%H:%M:%S') if event.timestamp else "Unknown",
            'impact': 0,
            'running_total': 0
        }
        
        # Determine if this is an O-line or D-line point
        is_o_line = point.our_line_type == 'O-line'
        
        # Update plus/minus based on event type
        if event.event_type in positive_events:
            event_data['impact'] = 1
            if is_o_line:
                o_line_plus_minus += 1
                event_data['running_total'] = o_line_plus_minus
                o_line_events.append(event_data)
            else:
                d_line_plus_minus += 1
                event_data['running_total'] = d_line_plus_minus
                d_line_events.append(event_data)
        elif event.event_type in negative_events:
            event_data['impact'] = -1
            if is_o_line:
                o_line_plus_minus -= 1
                event_data['running_total'] = o_line_plus_minus
                o_line_events.append(event_data)
            else:
                d_line_plus_minus -= 1
                event_data['running_total'] = d_line_plus_minus
                d_line_events.append(event_data)
    
    # Get throws data for completeness (in case throwaways are tracked there)
    throws_query = Throw.query.filter_by(
        thrower_id=player.id,
        team_organization_id=get_current_team_id()
    )
    if games:
        if isinstance(games, list):
            point_ids = [p.id for g in games for p in g.points]
        else:
            point_ids = [p.id for p in games.points]
        throws_query = throws_query.filter(Throw.point_id.in_(point_ids))
    
    # Process throws that are throwaways
    throwaway_events = []
    for throw in throws_query.filter_by(throw_type='throwaway').order_by(Throw.created_at).all():
        # Get the point for this throw
        point = Point.query.filter_by(
            id=throw.point_id,
            team_organization_id=get_current_team_id()
        ).first()
        
        # Skip if point is None
        if not point:
            continue
            
        # Create event data for display
        event_data = {
            'point_id': point.id,
            'game_id': point.game_id,
            'game_description': f"Game #{point.game_id}" if point.game_id else "Unknown",
            'game_date': point.game.date.strftime('%Y-%m-%d') if point.game and hasattr(point.game, 'date') and point.game.date else "Unknown",
            'event_type': 'throwaway (from Throw model)',
            'timestamp': throw.created_at.strftime('%H:%M:%S') if throw.created_at else "Unknown",
            'impact': -1,
            'running_total': 0
        }
        
        # Determine if this is an O-line or D-line point
        is_o_line = point.our_line_type == 'O-line'
        
        # Update plus/minus based on throw type
        if is_o_line:
            o_line_plus_minus -= 1
            event_data['running_total'] = o_line_plus_minus
            o_line_events.append(event_data)
        else:
            d_line_plus_minus -= 1
            event_data['running_total'] = d_line_plus_minus
            d_line_events.append(event_data)
        
        throwaway_events.append(event_data)
    
    # Calculate per point stats
    o_line_plus_minus_per_point = o_line_plus_minus / len(o_line_points) if o_line_points else 0
    d_line_plus_minus_per_point = d_line_plus_minus / len(d_line_points) if d_line_points else 0
    
    # Get tournaments for filter
    tournaments = Tournament.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(Tournament.start_date.desc()).all()
    
    # Sort events by timestamp
    o_line_events.sort(key=lambda x: x['timestamp'] if x['timestamp'] != "Unknown" else "")
    d_line_events.sort(key=lambda x: x['timestamp'] if x['timestamp'] != "Unknown" else "")
    
    return render_template(
        'stats/debug_line_plus_minus.html',
        player=player,
        o_line_points=o_line_points,
        d_line_points=d_line_points,
        o_line_events=o_line_events,
        d_line_events=d_line_events,
        throwaway_events=throwaway_events,
        o_line_plus_minus=o_line_plus_minus,
        d_line_plus_minus=d_line_plus_minus,
        o_line_plus_minus_per_point=o_line_plus_minus_per_point,
        d_line_plus_minus_per_point=d_line_plus_minus_per_point,
        tournaments=tournaments,
        selected_tournament=tournament_id,
        selected_game=game_id,
        games=games
    )

def get_players_base_stats(players, games=None):
    """Get stats for multiple players in a single batch of queries"""
    print(f"Batch loading stats for {len(players)} players")
    player_ids = [p.id for p in players]
    
    # Determine point IDs if games are specified
    point_ids = None
    if games:
        if isinstance(games, list):
            point_ids = []
            for g in games:
                # Handle both regular attribute access and query objects
                try:
                    if hasattr(g.points, 'all'):
                        points = g.points.all()
                    else:
                        points = g.points
                    point_ids.extend([p.id for p in points])
                except Exception as e:
                    print(f"Error getting points for game {g.id}: {str(e)}")
        else:
            try:
                if hasattr(games.points, 'all'):
                    points = games.points.all()
                else:
                    points = games.points
                point_ids = [p.id for p in points]
            except Exception as e:
                print(f"Error getting points for game: {str(e)}")
    
    # 1. Preload all lineups for these players in one query
    lineup_query = LineUp.query.filter(
        LineUp.player_id.in_(player_ids),
        LineUp.team_organization_id == get_current_team_id()
    )
    if point_ids:
        lineup_query = lineup_query.filter(LineUp.point_id.in_(point_ids))
    
    # Eager load related point data for line type determination
    lineup_query = lineup_query.options(db.joinedload(LineUp.point))
    
    # Group lineups by player_id
    lineups_by_player = {}
    for lineup in lineup_query.all():
        if lineup.player_id not in lineups_by_player:
            lineups_by_player[lineup.player_id] = []
        lineups_by_player[lineup.player_id].append(lineup)
    
    # 2. Preload all throws by these players in one query
    throws_query = Throw.query.filter(
        (Throw.thrower_id.in_(player_ids)) | 
        (Throw.receiver_id.in_(player_ids)),
        Throw.team_organization_id == get_current_team_id()
    )
    if point_ids:
        throws_query = throws_query.filter(Throw.point_id.in_(point_ids))
    
    # Group throws by thrower_id and receiver_id
    throws_by_thrower = {}
    throws_by_receiver = {}
    for throw in throws_query.all():
        if throw.thrower_id in player_ids:
            if throw.thrower_id not in throws_by_thrower:
                throws_by_thrower[throw.thrower_id] = []
            throws_by_thrower[throw.thrower_id].append(throw)
        
        if throw.receiver_id and throw.receiver_id in player_ids:
            if throw.receiver_id not in throws_by_receiver:
                throws_by_receiver[throw.receiver_id] = []
            throws_by_receiver[throw.receiver_id].append(throw)
    
    # 3. Preload all events for these players in one query
    events_query = Event.query.filter(
        Event.player_id.in_(player_ids),
        Event.team_organization_id == get_current_team_id()
    )
    if point_ids:
        events_query = events_query.filter(Event.point_id.in_(point_ids))
    
    # Group events by player_id
    events_by_player = {}
    for event in events_query.all():
        if event.player_id not in events_by_player:
            events_by_player[event.player_id] = []
        events_by_player[event.player_id].append(event)
    
    # 4. Process the preloaded data for each player
    player_stats = {}
    for player in players:
        player_stats[player.id] = process_player_stats(
            player, 
            lineups_by_player.get(player.id, []),
            throws_by_thrower.get(player.id, []),
            throws_by_receiver.get(player.id, []),
            events_by_player.get(player.id, []),
            games
        )
    
    return player_stats

def process_player_stats(player, lineups, throws_by_player, throws_to_player, events, games=None):
    """Process preloaded data for a single player"""
    # Start with default values for ALL possible stats
    stats = {
        # Basic stats
        'points_played': len(lineups),
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
        'throw_vectors': [],
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
        'highlight_plays': 0,
        
        # Direction stats
        'throw_directions': {
            'E': 0, 'ENE': 0, 'NE': 0, 'NNE': 0, 
            'N': 0, 'NNW': 0, 'NW': 0, 'WNW': 0, 
            'W': 0, 'WSW': 0, 'SW': 0, 'SSW': 0, 
            'S': 0, 'SSE': 0, 'SE': 0, 'ESE': 0
        },
        'completion_by_direction': {
            'E': 0, 'ENE': 0, 'NE': 0, 'NNE': 0, 
            'N': 0, 'NNW': 0, 'NW': 0, 'WNW': 0, 
            'W': 0, 'WSW': 0, 'SW': 0, 'SSW': 0, 
            'S': 0, 'SSE': 0, 'SE': 0, 'ESE': 0
        }
    }
    
    if stats['points_played'] == 0:
        return stats

    # Calculate games played
    if games:
        stats['games_played'] = len(games) if isinstance(games, list) else 1
    else:
        game_ids = set()
        for lineup in lineups:
            if hasattr(lineup.point, 'game_id'):
                game_ids.add(lineup.point.game_id)
        stats['games_played'] = len(game_ids)

    # Process throws
    stats['throws'] = len(throws_by_player)
    stats['completions'] = sum(1 for t in throws_by_player if t.is_completion)
    stats['assists'] = sum(1 for t in throws_by_player if t.throw_type == 'assist')
    stats['hockey_assists'] = sum(1 for t in throws_by_player if t.throw_type == 'hockey_assist')
    stats['throwaways'] = sum(1 for t in throws_by_player if t.throw_type == 'throwaway')
    stats['break_throws'] = sum(1 for t in throws_by_player if t.break_throw)
    
    # Calculate throw distances
    distances = [t.calculate_distance() for t in throws_by_player if t.calculate_distance()]
    stats['total_throw_distance'] = sum(distances) if distances else 0
    stats['avg_throw_distance'] = stats['total_throw_distance'] / stats['throws'] if stats['throws'] > 0 else 0
    
    # Store throw vectors for visualization
    stats['throw_vectors'] = [
        {
            'start_x': t.x_start,
            'start_y': t.y_start,
            'end_x': t.x_end,
            'end_y': t.y_end,
            'type': t.throw_type,
            'distance': t.calculate_distance() or 0
        }
        for t in throws_by_player if t.x_start is not None and t.y_start is not None and 
                                    t.x_end is not None and t.y_end is not None
    ]
    
    # Process throw directions
    for throw in throws_by_player:
        if throw.x_start is not None and throw.y_start is not None and throw.x_end is not None and throw.y_end is not None:
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
                    
            stats['throw_directions'][direction] += 1
            
            # If it's a completion, also increment completion count
            if throw.is_completion:
                stats['completion_by_direction'][direction] += 1
    
    # Process catches
    stats['catches'] = len(throws_to_player)
    
    # Process events
    for event in events:
        if event.event_type == 'goal':
            stats['goals'] += 1
        elif event.event_type == 'block':
            stats['blocks'] += 1
        elif event.event_type == 'drop':
            stats['drops'] += 1
        elif event.event_type == 'stall':
            stats['stalls'] += 1
        elif event.event_type == 'callahan':
            stats['callahans'] += 1
    
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
    
    # Calculate O-line and D-line stats
    o_line_points = [l for l in lineups if l.point.our_line_type == 'O-line']
    d_line_points = [l for l in lineups if l.point.our_line_type == 'D-line']
    
    stats['o_line_points_played'] = len(o_line_points)
    stats['d_line_points_played'] = len(d_line_points)
    
    # Calculate O-line and D-line plus/minus
    o_line_plus_minus = 0
    d_line_plus_minus = 0
    
    # Group events by point_id for more efficient processing
    events_by_point = {}
    for event in events:
        if event.point_id not in events_by_point:
            events_by_point[event.point_id] = []
        events_by_point[event.point_id].append(event)
    
    # Process each lineup to determine line type and calculate plus/minus
    for lineup in lineups:
        point = lineup.point
        is_o_line = point.our_line_type == 'O-line'
        
        # Get events for this point
        point_events = events_by_point.get(point.id, [])
        
        # Calculate plus/minus for this point
        point_plus_minus = 0
        for event in point_events:
            if event.event_type in ['goal', 'assist', 'block']:
                point_plus_minus += 1
            elif event.event_type in ['throwaway', 'drop', 'stall']:
                point_plus_minus -= 1
        
        # Add to the appropriate line's plus/minus
        if is_o_line:
            o_line_plus_minus += point_plus_minus
        else:
            d_line_plus_minus += point_plus_minus
    
    stats['o_line_plus_minus'] = o_line_plus_minus
    stats['d_line_plus_minus'] = d_line_plus_minus
    
    # Calculate per point stats
    if stats['o_line_points_played'] > 0:
        stats['o_line_plus_minus_per_point'] = stats['o_line_plus_minus'] / stats['o_line_points_played']
    if stats['d_line_points_played'] > 0:
        stats['d_line_plus_minus_per_point'] = stats['d_line_plus_minus'] / stats['d_line_points_played']
    
    # Calculate break throw percentage
    if stats['throws'] > 0:
        stats['break_throw_percentage'] = (stats['break_throws'] / stats['throws']) * 100
    
    return stats

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

@bp.route('/api/heatmap-data')
@login_required
def api_heatmap_data():
    """API endpoint for heatmap data filtered for the current user"""
    # Get the current user's player ID
    current_player_id = None
    if hasattr(current_user, 'player') and current_user.player:
        current_player_id = current_user.player.id
    
    # If no player profile is associated with the user, return empty data
    if not current_player_id:
        return jsonify([])
    
    # Get filter parameters
    opposition_team = request.args.get('opposition_team')
    
    # Process heatmap data specifically for the current player
    heatmap_data = process_heatmap_data(
        player_id=current_player_id,
        opposition_team=opposition_team,
        limit=1000
    )
    return jsonify(heatmap_data)

def generate_player_sankey_data(player_id, point_ids=None):
    """Generate Sankey diagram data for a specific player"""
    # Initialize data structure
    sankey_data = {
        "nodes": [],
        "links": []
    }
    
    # Get the player
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first()
    
    if not player:
        return sankey_data
    
    # Create a node for the current player
    player_node = {
        "id": f"player_{player.id}",
        "name": player.name,
        "jersey_number": player.jersey_number,
        "type": "current"
    }
    sankey_data["nodes"].append(player_node)
    
    # Track which nodes have been added to avoid duplicates
    added_node_ids = {f"player_{player.id}"}
    
    # Query for throws TO the player (incoming)
    incoming_query = Throw.query.filter_by(
        receiver_id=player.id,
        team_organization_id=get_current_team_id()
    )
    if point_ids:
        incoming_query = incoming_query.filter(Throw.point_id.in_(point_ids))
    
    # Query for throws FROM the player (outgoing)
    outgoing_query = Throw.query.filter_by(
        thrower_id=player.id,
        team_organization_id=get_current_team_id()
    )
    if point_ids:
        outgoing_query = outgoing_query.filter(Throw.point_id.in_(point_ids))
    
    # Process incoming throws
    thrower_counts = {}
    for throw in incoming_query.all():
        if throw.thrower_id:
            thrower_id = throw.thrower_id
            if thrower_id not in thrower_counts:
                thrower_counts[thrower_id] = 0
            thrower_counts[thrower_id] += 1
    
    # Process outgoing throws
    receiver_counts = {}
    for throw in outgoing_query.all():
        if throw.receiver_id:
            receiver_id = throw.receiver_id
            if receiver_id not in receiver_counts:
                receiver_counts[receiver_id] = 0
            receiver_counts[receiver_id] += 1
    
    # Add thrower nodes and links
    for thrower_id, count in thrower_counts.items():
        thrower = Player.query.filter_by(
            id=thrower_id,
            team_organization_id=get_current_team_id()
        ).first()
        
        if thrower:
            # Add thrower node
            node_id = f"thrower_{thrower.id}"
            
            # Only add the node if it hasn't been added yet
            if node_id not in added_node_ids:
                sankey_data["nodes"].append({
                    "id": node_id,
                    "name": thrower.name,
                    "jersey_number": thrower.jersey_number,
                    "type": "thrower"
                })
                added_node_ids.add(node_id)
            
            # Add link from thrower to player
            sankey_data["links"].append({
                "source": node_id,
                "target": f"player_{player.id}",
                "value": count
            })
    
    # Add receiver nodes and links
    for receiver_id, count in receiver_counts.items():
        receiver = Player.query.filter_by(
            id=receiver_id,
            team_organization_id=get_current_team_id()
        ).first()
        
        if receiver:
            # Add receiver node
            node_id = f"receiver_{receiver.id}"
            
            # Only add the node if it hasn't been added yet
            if node_id not in added_node_ids:
                sankey_data["nodes"].append({
                    "id": node_id,
                    "name": receiver.name,
                    "jersey_number": receiver.jersey_number,
                    "type": "receiver"
                })
                added_node_ids.add(node_id)
            
            # Add link from player to receiver
            sankey_data["links"].append({
                "source": f"player_{player.id}",
                "target": node_id,
                "value": count
            })
    
    return sankey_data




@bp.route('/api/player-connections-sankey/<int:player_id>')
@login_required
def api_player_connections_sankey(player_id): # <-- Accept player_id here
    """API endpoint for Sankey diagram showing player throw connections"""

    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    game_id = request.args.get('game_id', type=int)
    
    # Determine which games to analyze
    if game_id:
        games = [Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first()] if Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first() else []
    elif tournament_id:
        tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first()
        games = tournament.games.filter_by(
            team_organization_id=get_current_team_id()
        ).all() if tournament else []
    else:
        games = Game.query.filter_by(
            team_organization_id=get_current_team_id()
        ).all()
    
    # Get point IDs for filtering
    point_ids = get_point_ids_from_games(games)
    
    # Generate Sankey data using the player_id from the URL
    sankey_data = generate_player_sankey_data(player_id, point_ids)
    return jsonify(sankey_data)


@bp.route('/api/connection-data')
@login_required
def api_connection_data():
    """API endpoint for player connection data"""
    team_name = None
    if hasattr(current_user, 'player') and current_user.player:
        team_name = current_user.player.team
    
    # Get filter parameters
    opposition_team = request.args.get('opposition_team')
    min_connections = request.args.get('min_connections', 2, type=int)
    
    # Only include connections with at least min_connections throws
    connection_data = generate_player_connections(
        team_name=team_name, 
        opposition_team=opposition_team,
        min_connections=min_connections
    )
    return jsonify(connection_data)

@bp.route('/api/player-stats')
@login_required
def api_player_stats():
    """API endpoint for player stats table data"""
    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    game_id = request.args.get('game_id', type=int)
    
    # Determine which games to analyze
    if game_id:
        games = [Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first()] if Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first() else []
    elif tournament_id:
        tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first()
        games = tournament.games.filter_by(
            team_organization_id=get_current_team_id()
        ).all() if tournament else []
    else:
        games = Game.query.filter_by(
            team_organization_id=get_current_team_id()
        ).all()
    
    # Get team name from current user's player
    team_name = None
    if hasattr(current_user, 'player') and current_user.player:
        team_name = current_user.player.team
    
    # Get active players
    players_query = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    )
    if team_name:
        players_query = players_query.filter_by(team=team_name)
    players = players_query.all()
    
    # Get cached team averages
    team_avgs = get_cached_team_averages(games)
    
    # Get player stats in batch
    player_stats = get_players_base_stats(players, games)
    
    # Calculate PER for each player
    for player_id, stats in player_stats.items():
        if stats['points_played'] > 0:
            player = next((p for p in players if p.id == player_id), None)
            if player:
                stats['per'] = calculate_per(player, games, team_avgs)
    
    # Format data for DataTables
    result = []
    for player in players:
        if player.id in player_stats:
            stats = player_stats[player.id]
            if stats['points_played'] > 0:
                result.append({
                    'id': player.id,
                    'name': player.name,
                    'jersey_number': player.jersey_number,
                    'position': player.position,
                    'points_played': stats['points_played'],
                    'o_line_points': stats['o_line_points_played'],
                    'd_line_points': stats['d_line_points_played'],
                    'goals': stats['goals'],
                    'assists': stats['assists'],
                    'hockey_assists': stats['hockey_assists'],
                    'blocks': stats['blocks'],
                    'completions': stats['completions'],
                    'completion_rate': stats['completion_rate'],
                    'throwaways': stats['throwaways'],
                    'drops': stats['drops'],
                    'plus_minus': stats['plus_minus'],
                    'per': stats['per']
                })
    
    return jsonify(result)

def get_point_ids_from_games(games):
    """Safely extract point IDs from games, handling both lists and single games"""
    point_ids = []
    
    if not games:
        return point_ids
        
    if not isinstance(games, list):
        games = [games]
        
    for game in games:
        try:
            # Handle dynamic relationship
            if hasattr(game.points, 'all'):
                points = game.points.all()
            else:
                points = game.points
                
            point_ids.extend([p.id for p in points])
        except Exception as e:
            print(f"Error getting points for game {game.id}: {str(e)}")
            
    return point_ids

def calculate_most_common_throwaway_direction(player, games=None):
    """Analyzes throwaway throws to find the most common direction."""
    point_ids = get_point_ids_from_games(games)

    query = Throw.query.filter_by(
        thrower_id=player.id, 
        throw_type='throwaway',
        team_organization_id=get_current_team_id()
    )
    if point_ids:
        query = query.filter(Throw.point_id.in_(point_ids))
        
    throwaways = query.all()

    if not throwaways:
        return {"compass": "N/A", "field_relative": "N/A", "count": 0, "total": 0, "direction_data": {}}

    direction_counts = {
        'E': 0, 'ENE': 0, 'NE': 0, 'NNE': 0, 'N': 0, 'NNW': 0, 'NW': 0, 'WNW': 0,
        'W': 0, 'WSW': 0, 'SW': 0, 'SSW': 0, 'S': 0, 'SSE': 0, 'SE': 0, 'ESE': 0
    }
    
    # Define mapping from compass to field-relative directions
    field_direction_mapping = {
        'E': "Directly Upfield",
        'ENE': "Slightly Right Upfield",
        'NE': "Upfield Right",
        'NNE': "Far Right Upfield",
        'N': "Directly Right",
        'NNW': "Far Right Downfield",
        'NW': "Downfield Right",
        'WNW': "Slightly Right Downfield",
        'W': "Directly Downfield",
        'WSW': "Slightly Left Downfield",
        'SW': "Downfield Left",
        'SSW': "Far Left Downfield",
        'S': "Directly Left",
        'SSE': "Far Left Upfield",
        'SE': "Upfield Left",
        'ESE': "Slightly Left Upfield"
    }
    
    for throw in throwaways:
        if throw.x_start is not None and throw.y_start is not None and throw.x_end is not None and throw.y_end is not None:
            dx = throw.x_end - throw.x_start
            dy = throw.y_end - throw.y_start
            angle = math.atan2(dy, dx)
            degrees = (angle * 180 / math.pi + 360) % 360

            # Map angle to 16-point direction
            if degrees >= 348.75 or degrees < 11.25: direction = 'E'
            elif degrees >= 11.25 and degrees < 33.75: direction = 'ENE'
            elif degrees >= 33.75 and degrees < 56.25: direction = 'NE'
            elif degrees >= 56.25 and degrees < 78.75: direction = 'NNE'
            elif degrees >= 78.75 and degrees < 101.25: direction = 'N'
            elif degrees >= 101.25 and degrees < 123.75: direction = 'NNW'
            elif degrees >= 123.75 and degrees < 146.25: direction = 'NW'
            elif degrees >= 146.25 and degrees < 168.75: direction = 'WNW'
            elif degrees >= 168.75 and degrees < 191.25: direction = 'W'
            elif degrees >= 191.25 and degrees < 213.75: direction = 'WSW'
            elif degrees >= 213.75 and degrees < 236.25: direction = 'SW'
            elif degrees >= 236.25 and degrees < 258.75: direction = 'SSW'
            elif degrees >= 258.75 and degrees < 281.25: direction = 'S'
            elif degrees >= 281.25 and degrees < 303.75: direction = 'SSE'
            elif degrees >= 303.75 and degrees < 326.25: direction = 'SE'
            else: direction = 'ESE'
            
            direction_counts[direction] += 1

    if not any(direction_counts.values()):
        return {"compass": "N/A", "field_relative": "N/A", "count": 0, "total": 0, "direction_data": {}}

    most_common_direction = max(direction_counts, key=direction_counts.get)
    total_throwaways = sum(direction_counts.values())
    
    return {
        "compass": most_common_direction,
        "field_relative": field_direction_mapping[most_common_direction],
        "count": direction_counts[most_common_direction],
        "total": total_throwaways,
        "direction_data": direction_counts
    }

def calculate_most_common_throwaway_location(player, games=None):
    """Analyzes throwaway events to find the most common field zone."""
    point_ids = get_point_ids_from_games(games)
    
    query = Event.query.filter_by(
        player_id=player.id, 
        event_type='throwaway',
        team_organization_id=get_current_team_id()
    )
    if point_ids:
        query = query.filter(Event.point_id.in_(point_ids))
        
    throwaways = query.all()
    
    if not throwaways:
        return "N/A"

    # Define field zones
    x_zones = {
        (0, 20): "Own Endzone Area",
        (20, 40): "Defensive Third",
        (40, 60): "Midfield",
        (60, 80): "Attacking Third",
        (80, 100): "Opponent Endzone Area"
    }
    y_zones = {
        (0, 12): "Left Sideline",
        (12, 25): "Center of Field",
        (25, 37): "Right Sideline"
    }
    
    zone_counts = {}

    for event in throwaways:
        if event.field_position_x is not None and event.field_position_y is not None:
            x_pos, y_pos = event.field_position_x, event.field_position_y
            
            x_zone_name = next((name for (start, end), name in x_zones.items() if start <= x_pos < end), "Unknown X")
            y_zone_name = next((name for (start, end), name in y_zones.items() if start <= y_pos < end), "Unknown Y")
            
            zone_key = f"{y_zone_name}, {x_zone_name}"
            zone_counts[zone_key] = zone_counts.get(zone_key, 0) + 1
            
    if not zone_counts:
        return "N/A"
        
    # Find the most common zone
    most_common_zone = max(zone_counts, key=zone_counts.get)
    return most_common_zone

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

def calculate_line_efficiency(players, games, is_offensive=True):
    """Calculate line efficiency with gender separation"""
    player_efficiency = {}
    
    for player in players:
        # Get points where player was in lineup
        lineup_query = LineUp.query.join(Point).filter(
            LineUp.player_id == player.id,
            Point.our_line_type == ('O-line' if is_offensive else 'D-line'),
            LineUp.team_organization_id == get_current_team_id(),
            Point.team_organization_id == get_current_team_id()
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

@bp.route('/debug/point-outcomes/<int:game_id>')
@login_required
@admin_required # Or coach_required
def debug_point_outcomes(game_id):
    """Debug view to check point outcomes and events."""
    game = Game.query.get_or_404(game_id)
    points_data = []
    for point in game.points.order_by(Point.point_number):
        events = Event.query.filter_by(point_id=point.id).order_by(Event.timestamp).all()
        event_summary = [f"{e.event_type} by {e.player.name if e.player else 'N/A'}" for e in events]
        
        points_data.append({
            "point_number": point.point_number,
            "line_type": point.our_line_type,
            "we_scored_flag": point.we_scored, # The flag we are checking
            "point_outcome": point.point_outcome,
            "events": event_summary
        })
    return jsonify(points_data)


# In stats.py

@bp.route('/debug/offensive-stats/<int:player_id>')
@login_required
def debug_offensive_stats(player_id):
    """Debug page showing step-by-step offensive stat calculations."""
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    game_id = request.args.get('game_id', type=int)

    # Determine which games to analyze
    if game_id:
        game_obj = Game.query.get(game_id)
        games = [game_obj] if game_obj else []
    elif tournament_id:
        tournament = Tournament.query.get(tournament_id)
        games = tournament.games.all() if tournament else []
    else:
        games = Game.query.filter_by(team_organization_id=get_current_team_id()).all()

    # Get base stats and point IDs
    stats = get_players_base_stats([player], games).get(player.id, {})
    point_ids = get_point_ids_from_games(games)

    # --- Start Debug Info Calculation ---
    debug_info = {
        'raw_stats': {},
        'per_point_calcs': {},
        'conversion_rate_calcs': {}
    }

    # Populate raw stats used in calculations
    debug_info['raw_stats'] = {
        'goals': stats.get('goals', 0),
        'assists': stats.get('assists', 0),
        'throws': stats.get('throws', 0),
        'hucks': sum(1 for t in stats.get('throw_vectors', []) if t.get('distance', 0) > 20),
        'points_played': stats.get('points_played', 0),
        'o_line_points_played': stats.get('o_line_points_played', 0)
    }

    # Calculate Per-Point metrics step-by-step
    pp = debug_info['raw_stats']['points_played']
    debug_info['per_point_calcs'] = {
        'goals_per_point': (debug_info['raw_stats']['goals'] / pp) if pp > 0 else 0,
        'assists_per_point': (debug_info['raw_stats']['assists'] / pp) if pp > 0 else 0,
        'throws_per_point': (debug_info['raw_stats']['throws'] / pp) if pp > 0 else 0,
        'hucks_per_point': (debug_info['raw_stats']['hucks'] / pp) if pp > 0 else 0,
    }

    # Calculate O-Line Conversion Rate step-by-step
    olp = debug_info['raw_stats']['o_line_points_played']
    o_line_scores = 0
    if olp > 0:
        o_line_scores = Point.query.join(LineUp).filter(
            LineUp.player_id == player.id, Point.our_line_type == 'O-line',
            Point.id.in_(point_ids), Point.we_scored == True
        ).count()
    
    debug_info['conversion_rate_calcs'] = {
        'o_line_scores': o_line_scores,
        'result': (o_line_scores / olp * 100) if olp > 0 else 0
    }

    return render_template(
        'stats/debug_offensive_stats.html',
        player=player,
        stats=stats,
        debug_info=debug_info,
        selected_tournament=tournament_id,
        selected_game=game_id
    )
