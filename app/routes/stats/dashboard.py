from flask import render_template, flash
from flask_login import login_required, current_user
from app import db
from app.models.player import Player
from app.models.game import Game
import json
from app.utils.team_filter import get_current_team_id

from app.routes.stats import bp
from app.stats.cache import get_cached_team_averages
from app.stats.formulas import calculate_optimized_line_efficiency, calculate_per, calculate_team_avg_stats
from app.stats.players import get_players_base_stats
from app.stats.team import calculate_additional_team_metrics, calculate_game_stats, calculate_possession_based_team_metrics, calculate_team_summary, generate_player_connections, process_heatmap_data
from app.stats.loaders import preload_game_points


@bp.route('/')
@login_required
def index():
    team_id = get_current_team_id()
    players = Player.query.filter_by(active=True, team_organization_id=team_id).all()
    recent_games = (Game.query.filter_by(team_organization_id=team_id)
                    .options(db.joinedload(Game.tournament))
                    .order_by(Game.date.desc()).all())

    if not players or not recent_games:
        if not players:
            flash("No active players found", "warning")
        return render_template('stats/index.html', **EMPTY_CONTEXT)

    # Load every game's points (and events) in one go for the calculations below
    preload_game_points(recent_games)

    team_summary = calculate_team_summary(recent_games)
    team_summary.update(calculate_additional_team_metrics(recent_games))
    team_summary.update(calculate_possession_based_team_metrics(recent_games))

    team_stats = [{'stats': calculate_game_stats(game)} for game in recent_games[:5]]

    team_avgs = get_cached_team_averages(recent_games)
    player_stats = get_players_base_stats(players, recent_games)
    for stats in player_stats.values():
        if stats['points_played'] > 0:
            stats['per'] = calculate_per(stats, team_avgs)

    o_line_efficiency = calculate_optimized_line_efficiency(players, player_stats, is_offensive=True)
    d_line_efficiency = calculate_optimized_line_efficiency(players, player_stats, is_offensive=False)

    # Best four women and four men by line conversion; if gender isn't
    # recorded, the best seven overall.
    def best_line(efficiency):
        women = [p for p, _ in efficiency if p.gender == 'female'][:4]
        men = [p for p, _ in efficiency if p.gender == 'male'][:4]
        return women, men, (women + men if women or men else [p for p, _ in efficiency][:7])

    o_line_women, o_line_men, o_line_players = best_line(o_line_efficiency)
    d_line_women, d_line_men, d_line_players = best_line(d_line_efficiency)

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
        heatmap_data=json.dumps(process_heatmap_data(limit=1000)),
        connection_data=json.dumps(generate_player_connections()),
        team_avg_stats=calculate_team_avg_stats(player_stats),
        is_admin=current_user.is_admin,
        is_coach=current_user.is_coach,
    )


EMPTY_CONTEXT = {
    'team_summary': {
        'wins': 0, 'losses': 0, 'ties': 0, 'total_points': 0,
        'o_line_points': 0, 'o_line_conversions': 0,
        'd_line_points': 0, 'd_line_conversions': 0,
        'breaks': 0, 'win_percentage': 0,
        'o_line_conversion_rate': 0, 'd_line_conversion_rate': 0,
    },
    'players': [],
    'recent_games': [],
    'team_stats': [],
    'player_stats': {},
    'o_line_players': [],
    'd_line_players': [],
    'heatmap_data': [],
    'connection_data': {'nodes': [], 'links': []},
    'team_avg_stats': {},
}
