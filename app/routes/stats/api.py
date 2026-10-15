from flask import request, jsonify
from flask_login import login_required, current_user
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.utils.team_filter import get_current_team_id

from app.routes.stats import bp
from app.stats.cache import calculate_per, get_cached_team_averages
from app.stats.players import generate_player_sankey_data, get_players_base_stats, get_point_ids_from_games
from app.stats.team import generate_player_connections, process_heatmap_data


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
    # Get filter parameters
    opposition_team = request.args.get('opposition_team')
    min_connections = request.args.get('min_connections', 2, type=int)

    # team_organization_id scoping happens inside generate_player_connections via get_current_team_id()
    connection_data = generate_player_connections(
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
    
    # Get active players scoped to the current team organisation
    players = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    ).all()

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
