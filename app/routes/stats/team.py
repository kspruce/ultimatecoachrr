from flask import render_template, request
from flask_login import login_required
from app import db
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.utils.team_filter import get_current_team_id

from app.routes.stats import bp
from app.stats.formulas import calculate_per
from app.stats.cache import get_cached_team_averages
from app.stats.formulas import calculate_optimized_line_efficiency
from app.stats.players import get_players_base_stats
from app.stats.team import calculate_additional_team_metrics, calculate_performance_trends, calculate_possession_based_team_metrics, calculate_team_summary, get_previous_period_games
from app.stats.loaders import preload_game_points
from app.stats import turnovers


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
    
    # Load every game's points (and events) in one go for the calculations below
    preload_game_points(games)

    
  
    # Calculate team summary stats
    team_summary = calculate_team_summary(games)
    
    # Add additional metrics for radar charts
    team_summary.update(calculate_additional_team_metrics(games))
    
    # NEW: Add possession-based team metrics (clean hold, clean break, etc.)
    team_summary.update(calculate_possession_based_team_metrics(games))
    
    # Calculate previous period stats for comparison
    # (e.g., previous season or previous tournament)
    prev_games = get_previous_period_games(season, tournament_id)
    prev_summary = calculate_team_summary(prev_games)
    prev_metrics = calculate_additional_team_metrics(prev_games)
    
    # NEW: Previous-period possession metrics
    prev_poss_metrics = calculate_possession_based_team_metrics(prev_games)
    
    # Add previous metrics with 'prev_' prefix
    for key, value in prev_metrics.items():
        team_summary[f'prev_{key}'] = value
    for key, value in prev_summary.items():
        if key not in team_summary:
            team_summary[f'prev_{key}'] = value
    
    # NEW: add prev possession metrics too
    for key, value in prev_poss_metrics.items():
        team_summary[f'prev_{key}'] = value
    
    # Calculate player statistics scoped to the current team organisation
    players_query = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    )
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
                stats['per'] = calculate_per(stats, team_avgs)
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
    
    # Where the turnovers come from, what they cost, who's most secure,
    # and what to practise
    all_games = Game.query.filter_by(team_organization_id=get_current_team_id()).all()
    throwing = turnovers.ThrowingData(all_games)
    game_ids = {g.id for g in games}
    periods = turnovers.period_ids(all_games, tournament_id)
    ball_security = {
        'handling': turnovers.handling_summary(throwing, None, game_ids),
        'breakdown': turnovers.breakdown(throwing, None, game_ids),
        'zones': turnovers.zone_grid(throwing, None, game_ids),
        'cost': turnovers.turnover_cost(throwing, game_ids),
        'leaderboard': turnovers.turnover_leaderboard(throwing, players, game_ids),
        'practice': turnovers.practice_focus(
            throwing, periods['current'] if periods else game_ids, periods['baseline'] if periods else None),
        'practice_period': periods,
        'min_touches': turnovers.MIN_TOUCHES,
        'min_attempts': turnovers.MIN_ATTEMPTS,
    }
    # Trend over the games in the filter only
    ball_security['trends'] = turnovers.game_trends(throwing, None, game_ids)

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
        performance_trends=performance_trends,
        ball_security=ball_security,
    )
