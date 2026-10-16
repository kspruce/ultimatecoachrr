from flask import render_template
from flask_login import login_required
from app import db
from app.models.player import Player
from app.models.game import Game
from app.models.point import Point, LineUp
import json
from app.utils.team_filter import get_current_team_id

from app.routes.stats import bp
from app.stats.formulas import calculate_per
from app.stats.cache import get_cached_team_averages
from app.stats.formulas import calculate_impact_score
from app.stats.players import get_players_base_stats
from app.stats.team import calculate_additional_team_metrics, calculate_game_stats, generate_player_connections, process_heatmap_data
from app.stats.loaders import game_points


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
            stats['per'] = calculate_per(stats, team_avgs)
            player_stats.append({
                'player': player,
                'stats': stats
            })
    
    # Sort by points played
    player_stats.sort(key=lambda x: x['stats']['points_played'], reverse=True)
    
    # Generate visualization data — point_ids already scopes to this game,
    # so team_name filtering is redundant and Player.team doesn't exist anyway.
    point_ids = [p.id for p in game_points(game)]
    heatmap_data = process_heatmap_data(point_ids=point_ids)
    connection_data = generate_player_connections(point_ids=point_ids)
    
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
    )
