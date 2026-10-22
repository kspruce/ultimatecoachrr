from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.cutting_skill import CuttingSkill
from app.utils.team_filter import get_current_team_id

from app.routes.stats import bp
from app.stats.cache import get_cached_team_averages
from app.stats.formulas import calculate_per
from app.stats.history import get_player_game_history
from app.stats.players import calculate_cutting_stats, get_players_base_stats, get_point_ids_from_games
from app.stats import cutting, turnovers
from app.stats.team import calculate_additional_team_metrics, calculate_possession_based_team_metrics, calculate_team_summary


@bp.route('/player/<int:player_id>')
@login_required
def player_stats(player_id):
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Check if user has permission to view this player's stats
    if not (current_user.is_coach or (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player.id)):
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
        stats['per'] = calculate_per(stats, team_avgs)
    
    # Get point IDs for filtering if games are selected
    point_ids = get_point_ids_from_games(games)

    # --- Team-level summary calculations ---
    team_summary = calculate_team_summary(games)
    team_summary.update(calculate_additional_team_metrics(games))
    team_summary.update(calculate_possession_based_team_metrics(games))


    # --- Cutting Skills Calculations ---
    cutting_skills_query = CuttingSkill.query.filter_by(
        player_id=player_id,
        team_organization_id=get_current_team_id()
    )
    if point_ids:
        cutting_skills_query = cutting_skills_query.filter(CuttingSkill.point_id.in_(point_ids))
    cutting_skills = cutting_skills_query.all()
    # The detailed cut log (cut type picked by the stat-taker)
    cutting_stats = calculate_cutting_stats(
        [s for s in cutting_skills if s.cutting_type in CuttingSkill.DETAILED_CUTTING_TYPES])

    # --- Game History Calculation ---
    player_games = get_player_game_history(player, tournament_id, game_id)

    # --- Where the turnovers are: rates by bucket, vs team, over time ---
    all_games = Game.query.filter_by(team_organization_id=get_current_team_id()).all()
    throwing = turnovers.ThrowingData(all_games)
    game_ids = {g.id for g in games}
    periods = turnovers.period_ids(all_games, tournament_id, game_id,
                                   player_games=throwing.games_played[player.id])
    improvement = {
        'handling': turnovers.handling_summary(throwing, player.id, game_ids),
        'team_handling': turnovers.handling_summary(throwing, None, game_ids),
        'focus': turnovers.focus_areas(throwing, player.id, game_ids),
        'breakdown': turnovers.breakdown(throwing, player.id, game_ids),
        'zones': turnovers.zone_grid(throwing, player.id, game_ids),
        'directions': turnovers.direction_split(throwing, player.id, game_ids),
        'log': turnovers.turnover_log(throwing, player.id, game_ids),
        'trends': turnovers.game_trends(throwing, player.id),
        'comparison': periods and turnovers.compare_periods(
            throwing, player.id, periods['current'], periods['baseline'],
            periods['current_label'], periods['baseline_label']),
        'repeat': None if (game_id or tournament_id) else turnovers.repeat_focus(throwing, player.id, all_games),
    }

    # Cuts worked out from catches, plus the open-but-not-thrown-to taps
    cut_profile = cutting.cut_profile(throwing, player.id, game_ids)
    # Heatmap: where they caught it, and where logged cuts were made
    cutting_data = [{k: c[k] for k in ('cutting_type', 'outcome', 'field_position_x', 'field_position_y')}
                    for c in cut_profile.pop('cuts')]
    cutting_data += [skill.to_dict() for skill in cutting_skills
                     if skill.field_position_x is not None and skill.cutting_type != 'unspecified']

    # --- CORRECTED AND CONSOLIDATED RADAR CHART METRICS ---
    # This block ensures all necessary stats are calculated and correctly formatted.
    if stats['points_played'] > 0:
        # Offensive metrics
        stats['goals_per_point'] = stats['goals'] / stats['points_played']
        stats['assists_per_point'] = stats['assists'] / stats['points_played']
        stats['throws_per_point'] = stats['throws'] / stats['points_played']
        stats['hucks_per_point'] = stats.get('hucks', 0) / stats['points_played']
        stats['break_throw_percentage'] = (stats['break_throws'] / stats['throws'] * 100) if stats['throws'] > 0 else 0

        # Defensive metrics
        if stats['d_line_points_played'] > 0:
            stats['blocks_per_point'] = stats['blocks'] / stats['d_line_points_played']
            stats['turnovers_forced_per_point'] = (stats['blocks'] + stats['forced_turnovers']) / stats['d_line_points_played']
        else:
            stats['blocks_per_point'] = 0
            stats['turnovers_forced_per_point'] = 0
            
        # o_line_conversion_rate / d_line_conversion_rate come from the player stats
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

    # Enrich team_summary with per-point averages needed for radar chart comparison.
    # calculate_team_summary() only computes win/loss and line conversion rates; all
    # per-point metrics come from calculate_additional_team_metrics().
    if games:
        team_metrics = calculate_additional_team_metrics(games)
        for key in ['completion_rate', 'catch_rate', 'goals_per_point', 'assists_per_point',
                    'throws_per_point', 'hucks_per_point', 'blocks_per_point',
                    'turnovers_forced_per_point', 'break_throw_percentage', 'break_percentage']:
            team_summary[key] = team_metrics.get(key, 0)

    tournaments = Tournament.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(Tournament.start_date.desc()).all()

    # Add this right after calculating d_line_conversion_rate
    current_app.logger.debug(f"DEBUG: Player {player.name}")
    current_app.logger.debug(f"DEBUG: d_line_points_played = {stats['d_line_points_played']}")
    current_app.logger.debug(f"DEBUG: d_line_conversion_rate = {stats['d_line_conversion_rate']}")
    
    # Also print the point IDs to check if they match what we expect
    point_ids_list = [p_id for p_id in point_ids] if point_ids else []
    current_app.logger.debug(f"DEBUG: point_ids = {point_ids_list}")

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
        cut_profile=cut_profile,
        improvement=improvement,
    )
