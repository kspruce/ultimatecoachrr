"""Per-player stats built from recorded events, throws and lineups."""
from flask import current_app
from app import db
from app.models.player import Player
from app.models.point import LineUp
from app.models.event import Event
from app.models.throws import Throw
import math
from app.utils.team_filter import get_current_team_id
from app.stats.formulas import point_we_scored
from app.stats.loaders import preload_game_points, game_points




def get_players_base_stats(players, games=None):
    """Get stats for multiple players in a single batch of queries"""
    current_app.logger.debug(f"Batch loading stats for {len(players)} players")
    player_ids = [p.id for p in players]
    
    # Determine point IDs if games are specified
    # Games given but with no points (or none found) means no stats, not
    # every game's: an empty list still scopes the queries below.
    point_ids = None
    if games is not None:
        games = games if isinstance(games, list) else [games]
        preload_game_points(games)
        point_ids = [p.id for g in games for p in game_points(g)]

    # 1. Preload all lineups for these players in one query
    lineup_query = LineUp.query.filter(
        LineUp.player_id.in_(player_ids),
        LineUp.team_organization_id == get_current_team_id()
    )
    if point_ids is not None:
        lineup_query =lineup_query.filter(LineUp.point_id.in_(point_ids))
    
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
    if point_ids is not None:
        throws_query =throws_query.filter(Throw.point_id.in_(point_ids))
    
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
    if point_ids is not None:
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

# Same definition as the team huck count in app.stats.team.
HUCK_DISTANCE = 20  # metres


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
        'o_line_points_scored': 0,
        'd_line_points_scored': 0,
        'o_line_conversion_rate': 0,
        'd_line_conversion_rate': 0,
        
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

    # Games this player was on a line in (not the number of games in the filter)
    stats['games_played'] = len({lineup.point.game_id for lineup in lineups})

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
    stats['hucks'] = sum(1 for d in distances if d > HUCK_DISTANCE)
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
    # Conversion: share of their O-line points we held, D-line points we broke
    stats['o_line_points_scored'] = sum(1 for l in o_line_points if point_we_scored(l.point))
    stats['d_line_points_scored'] = sum(1 for l in d_line_points if point_we_scored(l.point))
    if o_line_points:
        stats['o_line_conversion_rate'] = 100 * stats['o_line_points_scored'] / len(o_line_points)
    if d_line_points:
        stats['d_line_conversion_rate'] = 100 * stats['d_line_points_scored'] / len(d_line_points)
    
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
            points = game_points(game)
                
            point_ids.extend([p.id for p in points])
        except Exception as e:
            current_app.logger.error(f"Error getting points for game {game.id}: {str(e)}")
            
    return point_ids
