"""Stats formulas and pages, on a season recorded through the stat-taker
endpoints (tests/stats_data.py)."""
import csv
import io

import pytest

from app import db, cache
from app.stats import formulas
from tests import stats_data


@pytest.fixture
def season(app):
    team = stats_data.build_team()
    admin = stats_data.build_admin(team)
    players = stats_data.build_players(team)
    client = stats_data.record_season(app, team, admin, players)
    return {'client': client, 'team_id': team.id, 'player_ids': [p.id for p in players]}


# --- formulas (no database) -------------------------------------------------

BASE = {'points_played': 10, 'goals': 2, 'assists': 3, 'hockey_assists': 1, 'throwaways': 1,
        'drops': 0, 'blocks': 1, 'stalls': 0, 'callahans': 0, 'completion_rate': 90.0,
        'catch_rate': 100.0, 'completions': 18, 'catches': 15,
        'o_line_points_played': 6, 'd_line_points_played': 4,
        'o_line_plus_minus_per_point': 0.5, 'd_line_plus_minus_per_point': 0.25}


def test_unadjusted_per_by_hand():
    w = formulas.PER_WEIGHTS
    box = (w['scoring'] * 2 ** 0.75 + w['assist'] * 3 ** 0.75 + w['assist'] * 0.5 * 1
           + w['turnover'] * 1 + w['defense'] * 1)
    passing = w['throw'] * (18 ** 0.75 * 0.9 ** 3 + 15 ** 0.75 * 1.0)
    assert formulas.calculate_unadjusted_per(BASE) == pytest.approx((box + passing) / 10)


def test_per_is_15_for_an_average_player():
    team_avgs = {'avg_uper': formulas.calculate_unadjusted_per(BASE),
                 'avg_o_line_plus_minus_per_point': 0.5,
                 'avg_d_line_plus_minus_per_point': 0.25}
    assert formulas.calculate_per(BASE, team_avgs) == pytest.approx(15)


def test_per_rewards_better_plus_minus_than_team():
    team_avgs = {'avg_uper': formulas.calculate_unadjusted_per(BASE),
                 'avg_o_line_plus_minus_per_point': 0.0, 'avg_d_line_plus_minus_per_point': 0.0}
    assert formulas.calculate_per(BASE, team_avgs) > 15
    assert formulas.calculate_per({**BASE, 'points_played': 0}, team_avgs) == 0


def test_line_efficiency_ranks_by_conversion():
    class P:
        def __init__(self, pid):
            self.id = pid
    a, b, c = P(1), P(2), P(3)
    stats = {1: {'o_line_points_played': 4, 'o_line_points_scored': 2},
             2: {'o_line_points_played': 4, 'o_line_points_scored': 3},
             3: {'o_line_points_played': 0, 'o_line_points_scored': 0}}
    ranked = formulas.calculate_optimized_line_efficiency([a, b, c], stats, is_offensive=True)
    assert ranked == [(b, 0.75), (a, 0.5)]


# --- pages ------------------------------------------------------------------

def test_stats_pages_render(app, season):
    client = season['client']
    pid = season['player_ids'][0]
    for url in ['/stats/', '/stats/team', '/stats/team?season=2026', f'/stats/player/{pid}',
                '/stats/game/1', '/stats/api/player-stats', '/stats/api/connection-data']:
        assert client.get(url).status_code == 200, url


def test_team_csv_export_works_and_fills_every_column(app, season):
    r = season['client'].get('/stats/team/export.csv')
    assert r.status_code == 200 and r.mimetype == 'text/csv'
    rows = list(csv.DictReader(io.StringIO(r.get_data(as_text=True))))
    assert rows
    # games_played is the games each player was in, not the number of games
    from app.models.player import Player
    from app.models.point import Point, LineUp
    for row in rows:
        player = Player.query.filter_by(name=row['name']).one()
        games = {gid for (gid,) in db.session.query(Point.game_id).join(LineUp)
                 .filter(LineUp.player_id == player.id).distinct()}
        assert int(row['games_played']) == len(games)
    assert any(float(row['goals_per_point']) > 0 for row in rows)
    assert any(float(row['o_line_conversion_rate']) > 0 for row in rows)
    assert any(int(row['hucks']) > 0 for row in rows)


def test_per_matches_between_dashboard_api_and_game_csv(app, season):
    """Every page now uses the same player stats and formula."""
    client = season['client']
    api = client.get('/stats/api/player-stats?game_id=1').get_json()
    game_csv = {row['name']: float(row['per']) for row in csv.DictReader(io.StringIO(
        client.get('/stats/game/1/export.csv').get_data(as_text=True)))}
    api_rows = api if isinstance(api, list) else api.get('players', api.get('data', []))
    compared = 0
    for row in api_rows:
        name, per = row.get('name'), row.get('per')
        if name in game_csv and per is not None:
            assert round(per, 2) == pytest.approx(game_csv[name], abs=0.011)
            compared += 1
    assert compared


def test_player_radar_conversion_rates_are_not_zero(app, season):
    client = season['client']
    page = client.get(f"/stats/player/{season['player_ids'][1]}").get_data(as_text=True)
    assert "'O-Line Conversion': 0.0," not in page or "'D-Line Conversion': 0.0," not in page


def test_recording_a_point_clears_the_stats_cache(app, season):
    from app.stats.cache import _cached_team_averages
    from flask import g  # noqa: F401
    client = season['client']
    client.get('/stats/')  # fills the team averages cache
    with app.test_request_context():
        key = _cached_team_averages.make_cache_key(_cached_team_averages.uncached,
                                                   season['team_id'], None)
    calls = {'n': 0}
    original = cache.delete_memoized

    def spy(*a, **kw):
        calls['n'] += 1
        return original(*a, **kw)
    cache.delete_memoized = spy
    try:
        from app.models.player import Player
        player = db.session.get(Player, season['player_ids'][0])
        player.notes = 'changed'
        db.session.commit()
    finally:
        cache.delete_memoized = original
    assert calls['n'] == 1, key


def test_maintenance_routes_need_post(app, season):
    client = season['client']
    assert client.get('/stats/admin/mark_break_throws').status_code == 405
    assert client.get('/stats/admin/recalculate_throw_distances').status_code == 405
    r = client.post('/stats/admin/recalculate_throw_distances')
    assert r.status_code == 302
    for url in ['/stats/admin/fix_missing_team_ids', '/stats/admin/reset_all_sequences',
                '/gameday/admin/fix_missing_team_ids', '/gameday/admin/reset_all_sequences',
                '/stats/debug/break_throws']:
        assert client.get(url).status_code == 404, url


def test_no_two_stats_routes_share_a_url(app):
    # The stats and stat-recording blueprints both live under /stats.
    seen = {}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith('/stats'):
            continue
        for method in rule.methods - {'HEAD', 'OPTIONS'}:
            key = (rule.rule, method)
            assert key not in seen, f'{rule.rule} {method}: {seen.get(key)} and {rule.endpoint}'
            seen[key] = rule.endpoint


def test_undoing_a_goal_reopens_the_point(app, season):
    from app.models.point import Point
    client = season['client']
    point = Point.query.filter_by(point_outcome='scored').order_by(Point.id.desc()).first()
    point_id = point.id
    # The last recorded point ended with a goal or scored_on; undo its last event.
    r = client.post(f'/stats/undo_event/{point_id}')
    assert r.status_code == 200, r.get_data(as_text=True)
    db.session.expire_all()
    assert db.session.get(Point, point_id).point_outcome is None
