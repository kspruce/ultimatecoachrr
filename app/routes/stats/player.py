from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.cutting_skill import CuttingSkill
from app.models.point import LineUp
from app.utils.team_filter import get_current_team_id
from app.utils.season import scope_games, scope_tournaments

from app.routes.stats import bp
from app.stats.cache import get_cached_team_averages
from app.stats.formulas import PER_SCALE, apply_ratings
from app.stats.history import get_player_game_history
from app.stats.players import calculate_cutting_stats, get_players_base_stats, get_point_ids_from_games
from app.stats import cutting, turnovers
from app.stats.profile import radar_profile, rating_comparison


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
        game = Game.query.filter_by(id=game_id, team_organization_id=get_current_team_id()).first()
        games = [game] if game else []
    elif tournament_id:
        tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first()
        games = tournament.games.filter_by(
            team_organization_id=get_current_team_id()
        ).all() if tournament else []
    else:
        # The season (and squad) being viewed
        games = scope_games(Game.query.filter_by(
            team_organization_id=get_current_team_id()
        )).all()

    # Everyone who played in these games: the player's teammates are what
    # the radars and ratings are ranked against
    point_ids = get_point_ids_from_games(games)
    peer_ids = {pid for (pid,) in LineUp.query.with_entities(LineUp.player_id).filter(
        LineUp.point_id.in_(point_ids),
        LineUp.team_organization_id == get_current_team_id()).distinct()} if point_ids else set()
    peers = Player.query.filter(Player.id.in_(peer_ids - {player.id}),
                                Player.team_organization_id == get_current_team_id()).all()
    stats_by_player = get_players_base_stats([player] + peers, games)
    stats = stats_by_player[player.id]

    # Ratings are measured against the team's averages for these games
    team_avgs = get_cached_team_averages(games)
    for peer_stats in stats_by_player.values():
        if peer_stats['points_played'] > 0:
            apply_ratings(peer_stats, team_avgs)

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

    # Radars and ratings: each as a percentile / rank among teammates
    profile = radar_profile(player.id, stats_by_player, throwing, game_ids)
    ratings = rating_comparison(player.id, stats_by_player)

    tournaments = scope_tournaments(Tournament.query.filter_by(
        team_organization_id=get_current_team_id()
    )).order_by(Tournament.start_date.desc()).all()

    return render_template(
        'stats/player_stats.html',
        player=player,
        stats=stats,
        # The team's PER for these games (an average player), for colouring PER
        team_per=PER_SCALE * team_avgs.get('avg_ge_per_point', 0),
        profile=profile,
        ratings=ratings,
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
