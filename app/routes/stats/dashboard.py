from flask import render_template, flash
from flask_login import login_required, current_user
from app import db
from app.models.game import Game
from app.utils.team_filter import get_current_team_id

from app.routes.stats import bp
from app.stats.cache import get_cached_team_averages
from app.stats.formulas import DEFAULT_SE, PER_PRIOR_POINTS, PER_SCALE, apply_ratings, ge_coefficients
from app.stats.players import get_players_base_stats, players_in_games
from app.utils.season import scope_games, season_players, viewing_season, viewing_squad
from app.stats.team import find_incomplete_points, calculate_game_stats, get_previous_period_games
from app.stats import dashboard as dash, turnovers
from app.stats.loaders import preload_game_points


@bp.route('/')
@login_required
def index():
    team_id = get_current_team_id()
    # The season (and squad) being viewed; all time if "All time" is picked
    season, squad = viewing_season(team_id), viewing_squad(team_id)
    games = (scope_games(Game.query.filter_by(team_organization_id=team_id), team_id)
             .options(db.joinedload(Game.tournament))
             .order_by(Game.date.desc()).all())

    if not games:
        if season is not None:
            flash(f"No games in the {season.name} season yet. Pick another season from the season menu to see "
                  "earlier stats.", "info")
        else:
            flash("No games recorded yet.", "info")
        return render_template('stats/index.html', has_games=False)

    preload_game_points(games)
    game_ids = {g.id for g in games}
    prev_games = get_previous_period_games(season, None, squad) if season is not None else []
    throwing = turnovers.ThrowingData(games + prev_games)

    # Everyone who played in these games: the group every average, median
    # and percentile on the stats pages is measured over
    players = players_in_games(games)
    team_avgs = get_cached_team_averages(games)
    stats_by_player = get_players_base_stats(players, games)
    for stats in stats_by_player.values():
        if stats['points_played'] > 0:
            apply_ratings(stats, team_avgs)

    # Coaches (and accounts without a player) see everyone; a player sees
    # their own row against the team's medians
    sees_all = current_user.is_coach or not current_user.player
    table = dash.player_table(players, stats_by_player, throwing, game_ids)
    if not sees_all:
        table['rows'] = [r for r in table['rows'] if r['player'].id == current_user.player.id]

    recent = [g for g in games if g.is_played][:8]
    prev_label = "the season before" if prev_games else None
    return render_template(
        'stats/index.html',
        has_games=True,
        season=season,
        games_count=sum(1 for g in games if g.is_played),
        headline=dash.headline(throwing, games, prev_games, prev_label),
        coverage=dash.coverage(throwing, games),
        incomplete=len(find_incomplete_points(games)),
        recent_games=[(g, calculate_game_stats(g)) for g in recent],
        table=table,
        leaders=dash.leaders(table, throwing, game_ids) if sees_all else None,
        line_usage=dash.line_usage(table) if sees_all else None,
        field=dash.field_maps(throwing, game_ids),
        pairs=dash.throwing_pairs(throwing, game_ids, {p.id: p for p in players}),
        sees_all=sees_all,
    )


@bp.route('/ratings')
@login_required
def ratings():
    """How the player ratings (SE, goal equivalents, EPM, PER, Eff) are
    worked out, with this team's own numbers for the season being viewed."""
    team_id = get_current_team_id()
    games = scope_games(Game.query.filter_by(team_organization_id=team_id), team_id).all()
    team_avgs = get_cached_team_averages(games) if games else {}
    se = team_avgs.get('se', DEFAULT_SE)

    # A worked example: your own line if you're a player, otherwise the
    # player with the most recorded points (players only see their own).
    example_player = example_stats = None
    if games:
        if current_user.player and not current_user.is_coach:
            candidates = [current_user.player]
        else:
            candidates = season_players(team_id)
        stats_by_id = get_players_base_stats(candidates, games) if candidates else {}
        recorded = [p for p in candidates if stats_by_id.get(p.id, {}).get('analysed_points', 0) > 0]
        if recorded:
            example_player = max(recorded, key=lambda p: stats_by_id[p.id]['analysed_points'])
            example_stats = apply_ratings(stats_by_id[example_player.id], team_avgs)

    return render_template(
        'stats/ratings.html',
        title='How the ratings work',
        season=viewing_season(team_id),
        has_games=bool(games),
        team_avgs=team_avgs,
        se=se,
        coeffs=ge_coefficients(se),
        reference=[(s, ge_coefficients(s)) for s in (0.4, 0.5, 0.6, 0.7, 0.8)],
        example_player=example_player,
        example=example_stats,
        incomplete=find_incomplete_points(games) if games else [],
        DEFAULT_SE=DEFAULT_SE,
        PER_PRIOR_POINTS=PER_PRIOR_POINTS,
        PER_SCALE=PER_SCALE,
    )
