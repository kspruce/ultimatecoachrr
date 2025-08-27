# app/utils/stats_calculator.py
from app.models.player import Player
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.event import Event
from app.models.stats import PlayerStats, TeamStats
from flask_login import current_user
import math

def get_current_team_id():
    """Get the current team organization ID from the logged-in user"""
    if current_user and hasattr(current_user, 'team_organization_id'):
        return current_user.team_organization_id
    return None

def get_players_base_stats(players, games=None):
    """
    Get comprehensive statistics for multiple players.
    
    Args:
        players: List of Player objects
        games: Optional list of Game objects to filter by
        
    Returns:
        Dictionary of player stats keyed by player ID
    """
    player_stats = {}
    
    for player in players:
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
            
            # Efficiency metrics
            'plus_minus': 0,
        }
        
        # Calculate points played
        lineup_query = LineUp.query.filter_by(player_id=player.id)
        if games:
            if isinstance(games, list):
                point_ids = []
                for game in games:
                    points = game.points.all() if hasattr(game.points, 'all') else game.points
                    point_ids.extend([p.id for p in points])
                lineup_query = lineup_query.filter(LineUp.point_id.in_(point_ids))
            else:
                points = games.points.all() if hasattr(games.points, 'all') else games.points
                point_ids = [p.id for p in points]
                lineup_query = lineup_query.filter(LineUp.point_id.in_(point_ids))
        
        lineups = lineup_query.all()
        stats['points_played'] = len(lineups)
        
        # Skip if player didn't play any points
        if stats['points_played'] == 0:
            player_stats[player.id] = stats
            continue
        
        # Calculate games played
        if games:
            stats['games_played'] = len(games) if isinstance(games, list) else 1
        else:
            game_ids = set()
            for lineup in lineups:
                if hasattr(lineup.point, 'game_id'):
                    game_ids.add(lineup.point.game_id)
            stats['games_played'] = len(game_ids)
        
        # Calculate O-line and D-line points
        o_line_points = [l for l in lineups if l.point.our_line_type == 'O-line']
        d_line_points = [l for l in lineups if l.point.our_line_type == 'D-line']
        
        stats['o_line_points_played'] = len(o_line_points)
        stats['d_line_points_played'] = len(d_line_points)
        
        # Calculate events
        events_query = Event.query.filter_by(player_id=player.id)
        if games:
            if isinstance(games, list):
                point_ids = []
                for game in games:
                    points = game.points.all() if hasattr(game.points, 'all') else game.points
                    point_ids.extend([p.id for p in points])
                events_query = events_query.filter(Event.point_id.in_(point_ids))
            else:
                points = games.points.all() if hasattr(games.points, 'all') else games.points
                point_ids = [p.id for p in points]
                events_query = events_query.filter(Event.point_id.in_(point_ids))
        
        events = events_query.all()
        
        # Count different event types
        for event in events:
            if event.event_type == 'goal':
                stats['goals'] += 1
            elif event.event_type == 'assist':
                stats['assists'] += 1
            elif event.event_type == 'hockey_assist':
                stats['hockey_assists'] += 1
            elif event.event_type == 'block':
                stats['blocks'] += 1
            elif event.event_type == 'throwaway':
                stats['throwaways'] += 1
            elif event.event_type == 'drop':
                stats['drops'] += 1
            elif event.event_type == 'catch':
                stats['catches'] += 1
            elif event.event_type == 'throw':
                stats['throws'] += 1
                stats['completions'] += 1
        
        # Add assists to throws and completions
        stats['throws'] += stats['assists']
        stats['completions'] += stats['assists']
        
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
        
        # Calculate O-line and D-line plus/minus
        for lineup in o_line_points:
            if lineup.point.we_scored:
                stats['o_line_plus_minus'] += 1
            else:
                stats['o_line_plus_minus'] -= 1
        
        for lineup in d_line_points:
            if lineup.point.we_scored:
                stats['d_line_plus_minus'] += 1
            else:
                stats['d_line_plus_minus'] -= 1
        
        # Calculate per point stats
        if stats['o_line_points_played'] > 0:
            stats['o_line_plus_minus_per_point'] = stats['o_line_plus_minus'] / stats['o_line_points_played']
        if stats['d_line_points_played'] > 0:
            stats['d_line_plus_minus_per_point'] = stats['d_line_plus_minus'] / stats['d_line_points_played']
        
        player_stats[player.id] = stats
    
    return player_stats

def calculate_team_summary(games):
    """
    Calculate team summary statistics.
    
    Args:
        games: List of Game objects
        
    Returns:
        Dictionary of team statistics
    """
    if not games:
        return {
            'games_played': 0,
            'wins': 0,
            'losses': 0,
            'ties': 0,
            'total_points': 0,
            'o_line_points': 0,
            'o_line_conversions': 0,
            'd_line_points': 0,
            'd_line_conversions': 0,
            'breaks': 0,
            'holds': 0,
            'win_percentage': 0,
            'o_line_conversion_rate': 0,
            'd_line_conversion_rate': 0
        }
    
    summary = {
        'games_played': len(games),
        'wins': sum(1 for g in games if hasattr(g, 'is_win') and g.is_win),
        'losses': sum(1 for g in games if hasattr(g, 'is_loss') and g.is_loss),
        'ties': sum(1 for g in games if hasattr(g, 'is_tie') and g.is_tie),
        'total_points': 0,
        'o_line_points': 0,
        'o_line_conversions': 0,
        'd_line_points': 0,
        'd_line_conversions': 0,
        'breaks': 0,
        'holds': 0
    }
    
    # Count points
    for game in games:
        try:
            points = game.points.all() if hasattr(game.points, 'all') else game.points
            summary['total_points'] += len(points)
            
            o_points = game.o_line_points.all() if hasattr(game.o_line_points, 'all') else game.o_line_points
            summary['o_line_points'] += len(o_points)
            summary['o_line_conversions'] += sum(1 for p in o_points if p.we_scored)
            
            d_points = game.d_line_points.all() if hasattr(game.d_line_points, 'all') else game.d_line_points
            summary['d_line_points'] += len(d_points)
            summary['d_line_conversions'] += sum(1 for p in d_points if p.we_scored)
            
            summary['breaks'] += sum(1 for p in points if hasattr(p, 'is_break') and p.is_break)
            summary['holds'] += sum(1 for p in points if hasattr(p, 'is_hold') and p.is_hold)
        except Exception as e:
            print(f"Error processing game {game.id}: {str(e)}")
    
    # Calculate percentages
    summary['win_percentage'] = (summary['wins'] / summary['games_played'] * 100) if summary['games_played'] > 0 else 0
    summary['o_line_conversion_rate'] = (summary['o_line_conversions'] / summary['o_line_points'] * 100) if summary['o_line_points'] > 0 else 0
    summary['d_line_conversion_rate'] = (summary['d_line_conversions'] / summary['d_line_points'] * 100) if summary['d_line_points'] > 0 else 0
    
    return summary

def calculate_additional_team_metrics(games):
    """
    Calculate additional team metrics for radar charts.
    
    Args:
        games: List of Game objects
        
    Returns:
        Dictionary of additional team metrics
    """
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
    
    # Get all point IDs
    point_ids = []
    total_points = 0
    for game in games:
        try:
            points = game.points.all() if hasattr(game.points, 'all') else game.points
            point_ids.extend([p.id for p in points])
            total_points += len(points)
        except Exception as e:
            print(f"Error getting points for game {game.id}: {str(e)}")
    
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
    
    # Get events
    events = Event.query.filter(Event.point_id.in_(point_ids)).all()
    
    # Count different event types
    goals = sum(1 for e in events if e.event_type == 'goal')
    assists = sum(1 for e in events if e.event_type == 'assist')
    blocks = sum(1 for e in events if e.event_type == 'block')
    throwaways = sum(1 for e in events if e.event_type == 'throwaway')
    drops = sum(1 for e in events if e.event_type == 'drop')
    stalls = sum(1 for e in events if e.event_type == 'stall')
    
    # Count throws and completions
    throws = sum(1 for e in events if e.event_type in ['throw', 'assist'])
    completions = throws  # All recorded throws and assists are completions
    
    # Count hucks (throws over 20m)
    hucks = sum(1 for e in events if e.event_type in ['throw', 'assist'] and hasattr(e, 'throw_distance') and e.throw_distance and e.throw_distance > 20)
    
    # Calculate completion rate
    completion_rate = (completions / (completions + throwaways) * 100) if (completions + throwaways) > 0 else 0
    
    # Calculate break percentage
    breaks = 0
    for game in games:
        try:
            points = game.points.all() if hasattr(game.points, 'all') else game.points
            breaks += sum(1 for p in points if hasattr(p, 'is_break') and p.is_break)
        except Exception as e:
            print(f"Error calculating breaks for game {game.id}: {str(e)}")
    
    break_percentage = (breaks / total_points * 100) if total_points > 0 else 0
    
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
    
    defensive_efficiency = (d_conversions / d_points_count * 100) if d_points_count > 0 else 0
    
    # Calculate per point metrics
    return {
        'completion_rate': completion_rate,
        'goals_per_point': goals / total_points,
        'assists_per_point': assists / total_points,
        'throws_per_point': throws / total_points,
        'hucks_per_point': hucks / total_points,
        'blocks_per_point': blocks / total_points,
        'turnovers_forced_per_point': (blocks + stalls) / total_points,
        'defensive_efficiency': defensive_efficiency,
        'break_percentage': break_percentage
    }

def calculate_team_averages(games):
    """
    Calculate team averages for PER normalization.
    
    Args:
        games: List of Game objects
        
    Returns:
        Dictionary of team averages
    """
    # Get all active players
    team_org_id = get_current_team_id()
    players = Player.query.filter_by(active=True, team_organization_id=team_org_id).all()
    
    # Get player stats
    player_stats = get_players_base_stats(players, games)
    
    # Calculate averages
    totals = {
        'o_line_plus_minus': 0,
        'o_line_points': 0,
        'd_line_plus_minus': 0,
        'd_line_points': 0,
        'uper_total': 0,
        'player_count': 0
    }
    
    for player_id, stats in player_stats.items():
        if stats['points_played'] > 0:
            totals['player_count'] += 1
            totals['o_line_plus_minus'] += stats.get('o_line_plus_minus', 0)
            totals['o_line_points'] += stats.get('o_line_points_played', 0)
            totals['d_line_plus_minus'] += stats.get('d_line_plus_minus', 0)
            totals['d_line_points'] += stats.get('d_line_points_played', 0)
            
            # Calculate raw PER for team average
            raw_per = calculate_unadjusted_per(stats)
            totals['uper_total'] += raw_per
    
    # Calculate averages
    avg_o_line_plus_minus_per_point = (totals['o_line_plus_minus'] / totals['o_line_points']) if totals['o_line_points'] > 0 else 0
    avg_d_line_plus_minus_per_point = (totals['d_line_plus_minus'] / totals['d_line_points']) if totals['d_line_points'] > 0 else 0
    avg_uper = totals['uper_total'] / totals['player_count'] if totals['player_count'] > 0 else 1
    
    return {
        'avg_o_line_plus_minus_per_point': avg_o_line_plus_minus_per_point,
        'avg_d_line_plus_minus_per_point': avg_d_line_plus_minus_per_point,
        'avg_uper': avg_uper
    }

def calculate_unadjusted_per(stats):
    """
    Calculate unadjusted Player Efficiency Rating (PER).
    
    Args:
        stats: Dictionary of player statistics
        
    Returns:
        float: Unadjusted PER value
    """
    if stats.get('points_played', 0) == 0:
        return 0
    
    # Define weights
    weights = {
        'scoring': 0.5,
        'assist': 0.5,
        'turnover': -0.75,
        'defense': 0.75,
        'throw': 0.05,
        'plus_minus': 0.1
    }
    
    # Box score components
    goals_component = weights['scoring'] * (stats.get('goals', 0) ** 0.75)
    assists_component = weights['assist'] * (stats.get('assists', 0) ** 0.75)
    hockey_assists_component = weights['assist'] * 0.5 * (stats.get('hockey_assists', 0) ** 0.75)
    turnovers_component = weights['turnover'] * ((stats.get('throwaways', 0) + stats.get('drops', 0)) ** 0.75)
    blocks_component = weights['defense'] * (stats.get('blocks', 0) ** 0.75)
    stalls_component = weights['defense'] * (-1) * (stats.get('stalls', 0) ** 0.75)
    callahans_component = 1.0 * (stats.get('callahans', 0) ** 0.75)
    
    box_component = goals_component + assists_component + hockey_assists_component + turnovers_component + blocks_component + stalls_component + callahans_component
    
    # Passing components
    completion_factor = (stats.get('completion_rate', 0) / 100) ** 3.0
    catch_factor = (stats.get('catch_rate', 0) / 100) ** 3.0
    completions_component = (stats.get('completions', 0) ** 0.75) * completion_factor
    catches_component = (stats.get('catches', 0) ** 0.75) * catch_factor
    passing_component = weights['throw'] * (completions_component + catches_component)
    
    # Calculate raw unadjusted PER
    raw_uper = (1 / stats['points_played']) * (box_component + passing_component)
    
    return raw_uper

def calculate_per_from_stats(stats, team_avgs):
    """
    Calculate PER using pre-loaded stats.
    
    Args:
        stats: Dictionary of player statistics
        team_avgs: Dictionary of team averages
        
    Returns:
        float: PER value
    """
    if stats.get('points_played', 0) == 0:
        return 0
    
    # Calculate unadjusted PER
    raw_per = calculate_unadjusted_per(stats)
    
    # Scale to league average of 15
    avg_uper = team_avgs.get('avg_uper', 1)
    if avg_uper <= 0:
        avg_uper = 1
    
    # Calculate adjusted PER
    adjusted_per = raw_per * (15 / avg_uper)
    
    return adjusted_per
