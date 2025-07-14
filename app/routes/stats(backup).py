from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from app import db
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.point import Point, LineUp
from app.models.event import Event
from sqlalchemy import func, distinct
import json
import math

bp = Blueprint('stats_dashboard', __name__, url_prefix='/stats')

# Helper functions
def count_player_events(player, event_types, games=None):
    """Count events of specific types for a player."""
    query = Event.query.filter(
        Event.player_id == player.id,
        Event.event_type.in_(event_types)
    )
    
    if games:
        game_ids = [g.id for g in games] if isinstance(games, list) else [games.id]
        query = query.join(Point).filter(Point.game_id.in_(game_ids))
        
    return query.count()

def normalize_per(per_value):
    """Normalize PER values to be within a reasonable range (0-30)."""
    if per_value > 100:
        return 100
    elif per_value < 0:
        return 0
    return per_value

def calculate_hockey_assists(player, games=None):
    """Calculate hockey assists for a player, handling None timestamps correctly."""
    hockey_assists = 0

    lineups = LineUp.query.filter_by(player_id=player.id).all()
    point_ids = [lineup.point_id for lineup in lineups]

    points_query = Point.query.filter(Point.id.in_(point_ids))
    if games:
        points_query = points_query.filter(Point.game_id.in_([g.id for g in games]))

    for point in points_query.all():
        events_query = Event.query.filter_by(point_id=point.id)
        
        # Only include events with timestamps for ordering and comparisons
        events = events_query.filter(Event.timestamp.isnot(None)).order_by(Event.timestamp).all()
        
        goal_events = [e for e in events if e.event_type == 'goal']

        for goal_event in goal_events:
            assist_events = [
                e for e in events 
                if e.event_type in ['throw', 'assist'] and 
                   e.receiver_id == goal_event.player_id and
                   e.timestamp is not None and # Handle potential NoneType
                   goal_event.timestamp is not None and # Handle potential NoneType
                   e.timestamp < goal_event.timestamp
            ]
            if assist_events:
                assist_event = sorted(assist_events, key=lambda e: e.timestamp, reverse=True)[0]
                hockey_assist_events = [
                    e for e in events 
                    if e.event_type in ['throw', 'assist'] and 
                       e.receiver_id == assist_event.player_id and
                       e.timestamp is not None and # Handle potential NoneType
                       assist_event.timestamp is not None and # Handle potential NoneType
                       e.timestamp < assist_event.timestamp
                ]
                if hockey_assist_events:
                    hockey_assist_event = sorted(hockey_assist_events, key=lambda e: e.timestamp, reverse=True)[0]
                    if hockey_assist_event.player_id == player.id:
                        hockey_assists += 1

    return hockey_assists

def calculate_throw_distance(player, games=None):
    """Calculate total and average throw distance, handling None timestamps."""
    throw_events_query = Event.query.filter(
        Event.player_id == player.id,
        Event.event_type.in_(['throw', 'assist'])
    )

    if games:
        game_ids = [g.id for g in games] if isinstance(games, list) else [games.id]
        throw_events_query = throw_events_query.join(Point).filter(Point.game_id.in_(game_ids))

    throw_events = throw_events_query.all()

    total_distance = 0
    count = 0

    for event in throw_events:
        if event.throw_distance:
            total_distance += event.throw_distance
            count += 1
        elif event.receiver_id:
            catch_event_query = Event.query.filter(
                Event.point_id == event.point_id,
                Event.player_id == event.receiver_id,
                Event.event_type.in_(['catch', 'goal'])
            )

            if event.timestamp: # Only filter by timestamp if it's not None
                catch_event_query = catch_event_query.filter(Event.timestamp > event.timestamp)

            catch_event = catch_event_query.order_by(Event.timestamp).first()

            if catch_event and catch_event.field_position_x is not None and catch_event.field_position_y is not None and event.field_position_x is not None and event.field_position_y is not None:
                # Calculate Euclidean distance
                dx = catch_event.field_position_x - event.field_position_x
                dy = catch_event.field_position_y - event.field_position_y
                distance = math.sqrt(dx*dx + dy*dy)
                total_distance += distance
                count += 1
                
                # Update the throw_distance in the database
                event.throw_distance = distance
                db.session.add(event)
    
    # Commit any throw distance updates
    db.session.commit()
    
    avg_distance = total_distance / count if count > 0 else 0
    return total_distance, avg_distance

def calculate_completion_rate(player, games=None):
    """Calculate completion rate for a player."""
    completions = count_player_events(player, ['throw', 'assist'], games)
    throwaways = count_player_events(player, ['throwaway'], games)
    
    if completions + throwaways > 0:
        return (completions / (completions + throwaways))
    else:
        return 0

def calculate_catch_rate(player, games=None):
    """Calculate catch rate for a player."""
    catches = count_player_events(player, ['catch', 'goal'], games)
    drops = count_player_events(player, ['drop'], games)
    
    if catches + drops > 0:
        return (catches / (catches + drops))
    else:
        return 0

def calculate_simple_per(player, games=None):
    """Calculate a simplified version of PER for the index page."""
    goals = count_player_events(player, ['goal'], games)
    assists = count_player_events(player, ['assist'], games)
    blocks = count_player_events(player, ['block'], games)
    throwaways = count_player_events(player, ['throwaway'], games)
    drops = count_player_events(player, ['drop'], games)
    stalls = count_player_events(player, ['stall'], games)  # Include stalls if you're tracking them

    # Simple +/- calculation, ensuring a 0 value if any counts are None
    return (goals or 0) + (assists or 0) + (blocks or 0) - (throwaways or 0) - (drops or 0) - (stalls or 0)

def calculate_o_d_line_stats(player, games=None):
    """Calculate o-line and d-line statistics for a player."""
    o_line_points_played = 0
    o_line_plus_minus = 0
    d_line_points_played = 0
    d_line_plus_minus = 0
    
    # Get all lineups for this player
    lineups_query = LineUp.query.filter_by(player_id=player.id).join(Point)
    
    if games:
        game_ids = [g.id for g in games] if isinstance(games, list) else [games.id]
        lineups_query = lineups_query.filter(Point.game_id.in_(game_ids))
    
    lineups = lineups_query.all()
    
    for lineup in lineups:
        point = lineup.point
        if point.our_line_type == 'O-line':
            o_line_points_played += 1
            o_line_plus_minus += (point.our_score_after - point.our_score_before) - (point.their_score_after - point.their_score_before)
        elif point.our_line_type == 'D-line':
            d_line_points_played += 1
            d_line_plus_minus += (point.our_score_after - point.our_score_before) - (point.their_score_after - point.their_score_before)
    
    return {
        'o_line_points_played': o_line_points_played,
        'o_line_plus_minus': o_line_plus_minus,
        'd_line_points_played': d_line_points_played,
        'd_line_plus_minus': d_line_plus_minus
    }


def calculate_unadjusted_per(player, games=None, team_avgs=None, points_played=None):
    """Calculate unadjusted PER for a player."""
    # Get points played if not provided
    if points_played is None:
        points_played_query = LineUp.query.filter_by(player_id=player.id)
        if games:
            game_ids = [g.id for g in games] if isinstance(games, list) else [games.id]
            points_played_query = points_played_query.join(Point).filter(Point.game_id.in_(game_ids))
        points_played = points_played_query.count()
    
    # Return 0 if player hasn't played any points
    if points_played == 0:
        return 0
    
    # Get basic stats
    goals = count_player_events(player, ['goal'], games)
    assists = count_player_events(player, ['assist'], games)
    drops = count_player_events(player, ['drop'], games)
    throwaways = count_player_events(player, ['throwaway'], games)
    blocks = count_player_events(player, ['block'], games)
    stalls = count_player_events(player, ['stall'], games)
    callahans = count_player_events(player, ['callahan'], games)
    
    # Get completions and catches
    completions = count_player_events(player, ['throw', 'assist'], games)
    catches = count_player_events(player, ['catch', 'goal'], games)
    
    # Calculate completion and catch rates
    completion_rate = calculate_completion_rate(player, games)
    catch_rate = calculate_catch_rate(player, games)
    
    # Get o-line and d-line stats
    od_stats = calculate_o_d_line_stats(player, games)
    
    # Calculate o-line and d-line plus-minus per point
    o_line_plus_minus_per_point = od_stats['o_line_plus_minus'] / od_stats['o_line_points_played'] if od_stats['o_line_points_played'] > 0 else 0
    d_line_plus_minus_per_point = od_stats['d_line_plus_minus'] / od_stats['d_line_points_played'] if od_stats['d_line_points_played'] > 0 else 0
    
    # Get team averages if not provided
    if team_avgs is None:
        players = Player.query.filter_by(active=True).all()
        team_avgs = calculate_team_averages(players, games)
    
    # Calculate unadjusted PER using the formula
    uper = (1 / points_played) * (
        (0.5 * (goals ** 0.75)) + 
        (0.5 * (assists ** 0.75)) - 
        (0.75 * (drops ** 0.75)) - 
        (0.75 * (throwaways ** 0.75)) + 
        (0.75 * (blocks ** 0.75)) - 
        (0.75 * (stalls ** 0.75)) + 
        (1.0 * (callahans ** 0.75)) + 
        0.05 * (
            (completions ** 0.75) * (completion_rate ** 3.0) + 
            (catches ** 0.75) * (catch_rate ** 3.0)
        ) + 
        0.1 * od_stats['o_line_points_played'] * (
            o_line_plus_minus_per_point - team_avgs['avg_o_line_plus_minus_per_point']
        ) + 
        0.1 * od_stats['d_line_points_played'] * (
            d_line_plus_minus_per_point - team_avgs['avg_d_line_plus_minus_per_point']
        )
    )
    
    return uper


def calculate_team_stats(game):
    """Calculate team statistics for a game."""
    stats = {
        'o_line_points': len(game.o_line_points),
        'o_line_conversions': sum(1 for p in game.o_line_points if p.we_scored),
        'd_line_points': len(game.d_line_points),
        'd_line_conversions': sum(1 for p in game.d_line_points if p.we_scored),
        'breaks': sum(1 for p in game.points if p.is_break),
        'holds': sum(1 for p in game.points if p.is_hold),
        'turnovers': 0,
        'possessions': 0,
        'turnover_rate': 0,
        'point_flow': []
    }
    
    # Calculate conversion rates
    if stats['o_line_points'] > 0:
        stats['o_line_conversion_rate'] = (stats['o_line_conversions'] / stats['o_line_points'] * 100)
    else:
        stats['o_line_conversion_rate'] = 0
        
    if stats['d_line_points'] > 0:
        stats['d_line_conversion_rate'] = (stats['d_line_conversions'] / stats['d_line_points'] * 100)
    else:
        stats['d_line_conversion_rate'] = 0
    
    return stats

def calculate_player_game_stats_basic(player, game):
    """Calculate basic statistics for a player in a specific game (for team averages)."""
    # Get points in this game
    points = Point.query.filter_by(game_id=game.id).all()
    point_ids = [p.id for p in points]
    
    # Get points played by this player in this game
    lineups = LineUp.query.filter(
        LineUp.player_id == player.id,
        LineUp.point_id.in_(point_ids)
    ).all()
    points_played = len(lineups)
    
    # Get events by this player in this game
    events = Event.query.filter(
        Event.player_id == player.id,
        Event.point_id.in_(point_ids)
    ).all()
    
    # Count different event types
    goals = sum(1 for e in events if e.event_type == 'goal')
    assists = sum(1 for e in events if e.event_type == 'assist')
    blocks = sum(1 for e in events if e.event_type == 'block')
    throwaways = sum(1 for e in events if e.event_type == 'throwaway')
    drops = sum(1 for e in events if e.event_type == 'drop')
    stalls = sum(1 for e in events if e.event_type == 'stall')
    
    # Calculate simple +/-
    plus_minus = goals + assists + blocks - throwaways - drops - stalls
    
    # Calculate o-line and d-line stats
    o_line_points_played = 0
    o_line_plus_minus = 0
    d_line_points_played = 0
    d_line_plus_minus = 0
    
    for lineup in lineups:
        point = lineup.point
        if point.our_line_type == 'O-line':
            o_line_points_played += 1
            o_line_plus_minus += (point.our_score_after - point.our_score_before) - (point.their_score_after - point.their_score_before)
        elif point.our_line_type == 'D-line':
            d_line_points_played += 1
            d_line_plus_minus += (point.our_score_after - point.our_score_before) - (point.their_score_after - point.their_score_before)
    
    # Calculate a simple unadjusted PER
    unadjusted_per = plus_minus
    
    return {
        'points_played': points_played,
        'goals': goals,
        'assists': assists,
        'blocks': blocks,
        'throwaways': throwaways,
        'drops': drops,
        'stalls': stalls,
        'o_line_points_played': o_line_points_played,
        'o_line_plus_minus': o_line_plus_minus,
        'd_line_points_played': d_line_points_played,
        'd_line_plus_minus': d_line_plus_minus,
        'unadjusted_per': unadjusted_per
    }


def calculate_player_stats(player, games=None, team_avgs=None):
    """Calculate statistics for a player across all games or specified games."""
    games_played_query = db.session.query(func.count(distinct(Point.game_id))).join(LineUp).filter(LineUp.player_id == player.id)
    if games:
        game_ids = [g.id for g in games] if isinstance(games, list) else [games.id]
        games_played_query = games_played_query.filter(Point.game_id.in_(game_ids))
    games_played = games_played_query.scalar() or 0
    
    points_played_query = LineUp.query.filter_by(player_id=player.id)
    if games:
        game_ids = [g.id for g in games] if isinstance(games, list) else [games.id]
        points_played_query = points_played_query.join(Point).filter(Point.game_id.in_(game_ids))
    points_played = points_played_query.count()
    
    goals = count_player_events(player, ['goal'], games)
    assists = count_player_events(player, ['assist'], games)
    blocks = count_player_events(player, ['block'], games)
    throwaways = count_player_events(player, ['throwaway'], games)
    drops = count_player_events(player, ['drop'], games)
    stalls = count_player_events(player, ['stall'], games)
    callahans = count_player_events(player, ['callahan'], games)
    completions = count_player_events(player, ['throw', 'assist'], games)
    catches = count_player_events(player, ['catch', 'goal'], games)
    turnovers = throwaways + drops + stalls
    hockey_assists = calculate_hockey_assists(player, games)
    total_throw_distance, avg_throw_distance = calculate_throw_distance(player, games)
    completion_rate = calculate_completion_rate(player, games) * 100  # Convert to percentage
    catch_rate = calculate_catch_rate(player, games) * 100  # Convert to percentage
    od_stats = calculate_o_d_line_stats(player, games)
    
    if not team_avgs:
        team_avgs = calculate_team_averages(games)
    
    o_line_plus_minus_per_point = od_stats['o_line_plus_minus'] / od_stats['o_line_points_played'] if od_stats['o_line_points_played'] > 0 else 0
    d_line_plus_minus_per_point = od_stats['d_line_plus_minus'] / od_stats['d_line_points_played'] if od_stats['d_line_points_played'] > 0 else 0
    
    if points_played > 0:
        unadjusted_per = (1 / points_played) * (
            (0.5 * (goals ** 0.75)) + 
            (0.5 * (assists ** 0.75)) - 
            (0.75 * (drops ** 0.75)) - 
            (0.75 * (throwaways ** 0.75)) + 
            (0.75 * (blocks ** 0.75)) - 
            (0.75 * (stalls ** 0.75)) + 
            (1.0 * (callahans ** 0.75)) + 
            0.05 * (
                (completions ** 0.75) * ((completion_rate/100) ** 3.0) + 
                (catches ** 0.75) * ((catch_rate/100) ** 3.0)
            ) + 
            0.1 * od_stats['o_line_points_played'] * (
                o_line_plus_minus_per_point - team_avgs['avg_o_line_plus_minus_per_point']
            ) + 
            0.1 * od_stats['d_line_points_played'] * (
                d_line_plus_minus_per_point - team_avgs['avg_d_line_plus_minus_per_point']
            )
        )
    else:
        unadjusted_per = 0
        
    per = normalize_per(unadjusted_per * (15 / team_avgs['avg_uper']) if team_avgs['avg_uper'] > 0 else 0)

    stats = {
        'games_played': games_played,
        'points_played': points_played,
        'goals': goals,
        'assists': assists,
        'hockey_assists': hockey_assists,
        'blocks': blocks,
        'throwaways': throwaways,
        'drops': drops,
        'stalls': stalls,
        'callahans': callahans,
        'catches': catches,
        'throws': completions,
        'completions': completions,
        'turnovers': turnovers,
        'total_throw_distance': total_throw_distance,
        'avg_throw_distance': avg_throw_distance,
        'completion_rate': completion_rate,
        'catch_rate': catch_rate,
        'o_line_points_played': od_stats['o_line_points_played'],
        'o_line_plus_minus': od_stats['o_line_plus_minus'],
        'd_line_points_played': od_stats['d_line_points_played'],
        'd_line_plus_minus': od_stats['d_line_plus_minus'],
        'unadjusted_per': unadjusted_per,
        'per': per
    }
    
    return stats

def calculate_player_game_stats(player, game):
    """Calculate statistics for a player in a specific game, including PER."""
    team_avgs = calculate_team_averages(games=[game]) # Calculate team averages for this game
    return calculate_player_stats(player, games=[game], team_avgs=team_avgs)  # Reuse the main stats function

def calculate_basic_team_averages(players, games=None):
    """Calculate basic team average statistics for PER calculation without recursion."""
    # This is now an alias for calculate_team_averages for backward compatibility
    return calculate_team_averages(games)

def calculate_team_averages(games=None):
    """Calculate team average statistics for PER calculation."""
    players = Player.query.filter_by(active=True).all()
    
    total_o_line_plus_minus_per_point = 0
    total_d_line_plus_minus_per_point = 0
    total_uper = 0
    player_count = 0
    
    for player in players:
        od_stats = calculate_o_d_line_stats(player, games)
        
        # Calculate o-line plus-minus per point
        if od_stats['o_line_points_played'] > 0:
            o_line_plus_minus_per_point = od_stats['o_line_plus_minus'] / od_stats['o_line_points_played']
            total_o_line_plus_minus_per_point += o_line_plus_minus_per_point
        
        # Calculate d-line plus-minus per point
        if od_stats['d_line_points_played'] > 0:
            d_line_plus_minus_per_point = od_stats['d_line_plus_minus'] / od_stats['d_line_points_played']
            total_d_line_plus_minus_per_point += d_line_plus_minus_per_point
        
        # Calculate simple +/- for team average calculation
        plus_minus = calculate_simple_per(player, games)
        total_uper = plus_minus
        player_count += 1
    
    # Calculate averages
    avg_o_line_plus_minus_per_point = total_o_line_plus_minus_per_point / player_count if player_count > 0 else 0
    avg_d_line_plus_minus_per_point = total_d_line_plus_minus_per_point / player_count if player_count > 0 else 0
    avg_uper = total_uper / player_count if player_count > 0 else 1  # Default to 1 to avoid division by zero
    
    return {
        'avg_o_line_plus_minus_per_point': avg_o_line_plus_minus_per_point,
        'avg_d_line_plus_minus_per_point': avg_d_line_plus_minus_per_point,
        'avg_uper': avg_uper
    }

@bp.route('/')
@login_required
def index():
    try:
        # Get active players
        players = Player.query.filter_by(active=True).all()
        if not players:
            print("No active players found")
            return render_template('stats/index.html', error="No active players found")

        # Get recent games
        recent_games = Game.query.order_by(Game.date.desc()).limit(5).all()
        if not recent_games:
            print("No recent games found")
            return render_template('stats/index.html', error="No recent games found")

        # Calculate team stats for recent games
        team_stats = []
        for game in recent_games:
            try:
                stats = calculate_team_stats(game)
                team_stats.append({
                    'game': game,
                    'stats': stats
                })
            except Exception as e:
                print(f"Error calculating team stats for game {game.id}: {str(e)}")
                continue

        # Calculate basic team averages first
        team_avgs = {
            'avg_o_line_plus_minus_per_point': 0,
            'avg_d_line_plus_minus_per_point': 0,
            'avg_uper': 1  # Default to 1 to avoid division by zero
        }

        # Then calculate player stats
        player_stats = {}
        total_uper = 0
        player_count = 0

        for player in players:
            try:
                # Calculate overall player stats
                overall_stats = calculate_player_stats(player, None, team_avgs)
                
                # Calculate game-specific stats
                player_game_stats = []
                for game in recent_games:
                    game_stats = calculate_player_game_stats(player, game)
                    player_game_stats.append({
                        'game': game,
                        'stats': game_stats
                    })

                player_stats[player.id] = {
                    'overall': overall_stats,
                    'game_stats': player_game_stats
                }

                if overall_stats['points_played'] > 0:
                    total_uper += overall_stats['unadjusted_per']
                    player_count += 1

            except Exception as e:
                print(f"Error calculating stats for player {player.id}: {str(e)}")
                continue

        # Update team averages with actual average uPER
        if player_count > 0:
            team_avgs['avg_uper'] = total_uper / player_count
            
            # Recalculate PER with updated average uPER
            for player in players:
                if player.id in player_stats:
                    stats = player_stats[player.id]['overall']
                    if 'unadjusted_per' in stats:
                        stats['per'] = normalize_per(
                            stats['unadjusted_per'] * (15 / team_avgs['avg_uper']) 
                            if team_avgs['avg_uper'] > 0 else 0
                        )

        # Find optimal O-line and D-line
        o_line_players = [p for p in players if p.line_preference in ['O-line', 'both']][:7]
        d_line_players = [p for p in players if p.line_preference in ['D-line', 'both']][:7]

        return render_template(
            'stats/index.html',
            players=players,
            recent_games=recent_games,
            team_stats=team_stats,
            player_stats=player_stats,
            o_line_players=o_line_players,
            d_line_players=d_line_players
        )

    except Exception as e:
        print(f"Error in index route: {str(e)}")
        return render_template('stats/index.html', error=f"An error occurred: {str(e)}")




@bp.route('/game/<int:game_id>')
@login_required
def game_stats(game_id):
    game = Game.query.get_or_404(game_id)
    
    # Calculate team statistics for the game
    team_stats = calculate_team_stats(game)
    
    # Calculate player statistics for the game
    player_stats = []
    players_in_game = set()
    
    for point in game.points:
        for lineup in point.lineups:
            players_in_game.add(lineup.player)
    
    for player in players_in_game:
        stats = calculate_player_game_stats(player, game)
        player_stats.append({
            'player': player,
            'stats': stats
        })
    
    # Sort player stats by points played
    player_stats.sort(key=lambda x: x['stats']['points_played'], reverse=True)
    
    # Generate heatmap data
    events = []
    for point in game.points:
        events.extend(point.events.all())
    
    heatmap_data = []
    for event in events:
        if event.field_position_x is not None and event.field_position_y is not None:
            heatmap_data.append({
                'x': event.field_position_x,
                'y': event.field_position_y,
                'value': 1,  # Each event has equal weight
                'event_type': event.event_type  # Include event type for filtering
            })
    
    # Generate player connection data
    player_ids = set()
    connections = {}
    
    # Count throws between players
    for event in events:
        if event.event_type in ['throw', 'assist'] and event.receiver_id:
            player_ids.add(event.player_id)
            player_ids.add(event.receiver_id)
            
            connection_key = f"{event.player_id}-{event.receiver_id}"
            if connection_key in connections:
                connections[connection_key] += 1
            else:
                connections[connection_key] = 1
    
    # Create nodes and links for D3 visualization
    nodes = []
    for player_id in player_ids:
        player = Player.query.get(player_id)
        if player:
            nodes.append({
                'id': player.id,
                'name': player.name,
                'jersey_number': player.jersey_number,
                'position': player.position
            })
    
    links = []
    for connection_key, value in connections.items():
        source_id, target_id = map(int, connection_key.split('-'))
        links.append({
            'source': source_id,
            'target': target_id,
            'value': value
        })
    
    connection_data = {
        'nodes': nodes,
        'links': links
    }
    
    # Add point flow data to team stats
    team_stats['point_flow'] = []
    for point in sorted(game.points, key=lambda p: p.point_number):
        team_stats['point_flow'].append({
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
    
    return render_template(
        'stats/game_stats.html',
        game=game,
        team_stats=team_stats,
        player_stats=player_stats,
        heatmap_data=json.dumps(heatmap_data),
        connections=json.dumps(connection_data)
    )


@bp.route('/player/<int:player_id>')
@login_required
def player_stats(player_id):
    player = Player.query.get_or_404(player_id)
    
    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    game_id = request.args.get('game_id', type=int)
    
    # Get games based on filters
    games = None
    if game_id:
        games = Game.query.get(game_id)
    elif tournament_id:
        tournament = Tournament.query.get(tournament_id)
        if tournament:
            games = tournament.games.all()
    
    # Calculate team averages
    team_avgs = calculate_team_averages(games)
    
    # Calculate statistics with team averages
    stats = calculate_player_stats(player, games, team_avgs)
    
    # Debug output
    print(f"Player: {player.name}")
    print(f"Overall PER: {stats.get('per', 'Not found')}")
    
    if stats.get('games_played', 0) == 0:
        return render_template('stats/no_stats.html', player=player)
    else:    
        # Get player's games
        player_games = []
        for game in Game.query.order_by(Game.date.desc()).all():
            # Check if player played in this game
            played = False
            for point in game.points:
                if player.id in [lineup.player_id for lineup in point.lineups]:
                    played = True
                    break
            
            if played:
                game_stats = calculate_player_game_stats(player, game)
                print(f"Game vs {game.opponent}: PER = {game_stats.get('per', 'Not found')}")
                player_games.append({
                    'game': game,
                    'stats': game_stats
                })
        
        # Get tournaments for filter
        tournaments = Tournament.query.order_by(Tournament.start_date.desc()).all()
        
    # Generate throw vector data with better debugging
    throw_vectors = []
    throwaway_locations = []
    
    # Get all events by this player
    events_query = Event.query.filter_by(player_id=player.id)
    if games:
        if isinstance(games, list):
            game_ids = [g.id for g in games]
            points = Point.query.filter(Point.game_id.in_(game_ids)).all()
        else:
            points = Point.query.filter_by(game_id=games.id).all()
        point_ids = [p.id for p in points]
        events_query = events_query.filter(Event.point_id.in_(point_ids))
    
    events = events_query.order_by(Event.timestamp).all()
    
    # Debug info
    print(f"Found {len(events)} events for player {player.name}")
    
    # Process events to find throw vectors and throwaway locations
    for i, event in enumerate(events):
        if event.event_type in ['throw', 'assist'] and event.field_position_x is not None and event.field_position_y is not None:
            # Find the next event (catch or goal) by the receiver
            if event.receiver_id:
                print(f"Processing throw by {player.name} to player {event.receiver_id}")
                
                # Get all events by the receiver in this point
                receiver_events = Event.query.filter(
                    Event.point_id == event.point_id,
                    Event.player_id == event.receiver_id,
                    Event.event_type.in_(['catch', 'goal'])
                ).all()
                
                print(f"Found {len(receiver_events)} potential catch events")
                
                # Find the first event after this throw
                next_event = None
                for recv_event in receiver_events:
                    if recv_event.timestamp and event.timestamp and recv_event.timestamp > event.timestamp:
                        if next_event is None or recv_event.timestamp < next_event.timestamp:
                            next_event = recv_event
                
                if next_event and next_event.field_position_x is not None and next_event.field_position_y is not None:
                    print(f"Found matching catch event at position ({next_event.field_position_x}, {next_event.field_position_y})")
                    
                    # Normalize coordinates (ensure they're between 0 and 1)
                    start_x = min(max(float(event.field_position_x), 0), 1)
                    start_y = min(max(float(event.field_position_y), 0), 1)
                    end_x = min(max(float(next_event.field_position_x), 0), 1)
                    end_y = min(max(float(next_event.field_position_y), 0), 1)
                    
                    # Add throw vector
                    throw_vectors.append({
                        'start_x': start_x,
                        'start_y': start_y,
                        'end_x': end_x,
                        'end_y': end_y,
                        'type': event.event_type
                    })
                    
                    print(f"Added throw vector: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
        
                    # Debug info
                    print(f"Generated {len(throw_vectors)} throw vectors")
        
            elif event.event_type == 'throwaway' and event.field_position_x is not None and event.field_position_y is not None:
                # Add throwaway location
                throwaway_locations.append({
                    'x': event.field_position_x,
                    'y': event.field_position_y
                })
                
                # Try to find the intended target (if any)
                # This is speculative - you might need to adjust based on your data model
                if i > 0 and events[i-1].event_type in ['catch', 'goal'] and events[i-1].field_position_x is not None and events[i-1].field_position_y is not None:
                    throwaway_locations[-1]['prev_x'] = events[i-1].field_position_x
                    throwaway_locations[-1]['prev_y'] = events[i-1].field_position_y
        
        # If no throw vectors were found, add some test data
        if not throw_vectors:
            print("No throw vectors found, adding test data")
            throw_vectors = [
                {'start_x': 0.3, 'start_y': 0.4, 'end_x': 0.6, 'end_y': 0.5, 'type': 'throw'},
                {'start_x': 0.2, 'start_y': 0.6, 'end_x': 0.4, 'end_y': 0.7, 'type': 'assist'},
                {'start_x': 0.7, 'start_y': 0.3, 'end_x': 0.8, 'end_y': 0.2, 'type': 'throw'}
            ]
        
        # If no throwaway locations were found, add some test data
        if not throwaway_locations:
            print("No throwaway locations found, adding test data")
            throwaway_locations = [
                {'x': 0.8, 'y': 0.8},
                {'x': 0.7, 'y': 0.3, 'prev_x': 0.6, 'prev_y': 0.2}
            ]        
        
        # Generate general heatmap data
        heatmap_data = []
        for event in events:
            if event.field_position_x is not None and event.field_position_y is not None:
                heatmap_data.append({
                    'x': event.field_position_x,
                    'y': event.field_position_y,
                    'value': 1,
                    'event_type': event.event_type
                })
    
    return render_template(
        'stats/player_stats.html',
        player=player,
        stats=stats,
        player_games=player_games,
        tournaments=tournaments,
        selected_tournament=tournament_id,
        selected_game=game_id,
        heatmap_data=json.dumps(heatmap_data),
        throw_vectors=json.dumps(throw_vectors),
        throwaway_locations=json.dumps(throwaway_locations)
    )

@bp.route('/team')
@login_required
def team_stats():
    # Get filter parameters
    season = request.args.get('season', '')
    tournament_id = request.args.get('tournament_id', type=int)
    
    # Get games based on filters
    games_query = Game.query
    if tournament_id:
        games_query = games_query.filter_by(tournament_id=tournament_id)
    elif season:
        tournament_ids = [t.id for t in Tournament.query.filter_by(season=season).all()]
        games_query = games_query.filter(Game.tournament_id.in_(tournament_ids))
    
    games = games_query.all()
    
    # Calculate player statistics across filtered games
    player_stats = []
    players = Player.query.filter_by(active=True).all()
    
    for player in players:
        stats = calculate_player_stats(player, games)  # This now includes the full PER calculation
        player_stats.append({
            'player': player,
            'stats': stats
        })
    
    # Sort player stats by PER
    player_stats.sort(key=lambda x: x['stats']['per'], reverse=True)
    
    # Calculate team summary stats
    total_points = sum(len(game.points.all()) for game in games)
    wins = sum(1 for game in games if game.is_win)
    losses = sum(1 for game in games if game.is_loss)
    ties = sum(1 for game in games if not game.is_win and not game.is_loss)
    
    o_line_points = sum(len(game.o_line_points) for game in games)
    o_line_conversions = sum(sum(1 for p in game.o_line_points if p.we_scored) for game in games)
    o_line_conversion_rate = (o_line_conversions / o_line_points * 100) if o_line_points > 0 else 0
    
    d_line_points = sum(len(game.d_line_points) for game in games)
    d_line_conversions = sum(sum(1 for p in game.d_line_points if p.we_scored) for game in games)
    d_line_conversion_rate = (d_line_conversions / d_line_points * 100) if d_line_points > 0 else 0
    
    team_summary = {
        'games_played': len(games),
        'total_points': total_points,
        'wins': wins,
        'losses': losses,
        'ties': ties,
        'win_percentage': (wins / len(games) * 100) if len(games) > 0 else 0,
        'o_line_points': o_line_points,
        'o_line_conversions': o_line_conversions,
        'o_line_conversion_rate': o_line_conversion_rate,
        'd_line_points': d_line_points,
        'd_line_conversions': d_line_conversions,
        'd_line_conversion_rate': d_line_conversion_rate
    }
    
    # Get tournaments and seasons for filters
    tournaments = Tournament.query.order_by(Tournament.start_date.desc()).all()
    seasons = db.session.query(Tournament.season).distinct().all()
    seasons = [s[0] for s in seasons if s[0]]
    
    # Find optimal O-line and D-line
    o_line_players = [p for p in players if p.line_preference in ['O-line', 'both']][:7]
    d_line_players = [p for p in players if p.line_preference in ['D-line', 'both']][:7]
    
    return render_template(
        'stats/team_stats.html',
        player_stats=player_stats,
        team_summary=team_summary,
        tournaments=tournaments,
        seasons=seasons,
        selected_tournament=tournament_id,
        selected_season=season,
        o_line_players=o_line_players,
        d_line_players=d_line_players
    )

@bp.route('/visualizations')
@login_required
def visualizations():
    # Get filter parameters
    game_id = request.args.get('game_id', type=int)
    tournament_id = request.args.get('tournament_id', type=int)
    player_id = request.args.get('player_id', type=int)
    
    # Get events based on filters
    events_query = Event.query
    
    if game_id:
        game = Game.query.get(game_id)
        if game:
            point_ids = [p.id for p in game.points]
            events_query = events_query.filter(Event.point_id.in_(point_ids))
    elif tournament_id:
        tournament = Tournament.query.get(tournament_id)
        if tournament:
            game_ids = [g.id for g in tournament.games]
            points = Point.query.filter(Point.game_id.in_(game_ids)).all()
            point_ids = [p.id for p in points]
            events_query = events_query.filter(Event.point_id.in_(point_ids))
    
    if player_id:
        events_query = events_query.filter_by(player_id=player_id)
    
    events = events_query.all()
    
    # Generate heatmap data
    heatmap_data = []
    for event in events:
        if event.field_position_x is not None and event.field_position_y is not None:
            heatmap_data.append({
                'x': event.field_position_x,
                'y': event.field_position_y,
                'value': 1,  # Each event has equal weight
                'event_type': event.event_type  # Include event type for filtering
            })
    
    # Generate player connection data
    player_ids = set()
    connections = {}
    
    # Count throws between players
    for event in events:
        if event.event_type in ['throw', 'assist'] and event.receiver_id:
            player_ids.add(event.player_id)
            player_ids.add(event.receiver_id)
            
            connection_key = f"{event.player_id}-{event.receiver_id}"
            if connection_key in connections:
                connections[connection_key] += 1
            else:
                connections[connection_key] = 1
    
    # Create nodes and links for D3 visualization
    nodes = []
    for player_id in player_ids:
        player = Player.query.get(player_id)
        if player:
            nodes.append({
                'id': player.id,
                'name': player.name,
                'jersey_number': player.jersey_number,
                'position': player.position
            })
    
    links = []
    for connection_key, value in connections.items():
        source_id, target_id = map(int, connection_key.split('-'))
        links.append({
            'source': source_id,
            'target': target_id,
            'value': value
        })
    
    connection_data = {
        'nodes': nodes,
        'links': links
    }
    
    # Get games, tournaments, and players for filters
    games = Game.query.order_by(Game.date.desc()).all()
    tournaments = Tournament.query.order_by(Tournament.start_date.desc()).all()
    players = Player.query.filter_by(active=True).order_by(Player.name).all()
    
    return render_template(
        'stats/visualizations.html',
        heatmap_data=json.dumps(heatmap_data),
        connections=json.dumps(connection_data),
        games=games,
        tournaments=tournaments,
        players=players,
        selected_game=game_id,
        selected_tournament=tournament_id,
        selected_player=player_id
    )


