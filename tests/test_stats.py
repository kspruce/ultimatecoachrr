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


def test_coefficients_match_bbsm_club_nationals():
    """The men's division at 2026 Club Nationals had G .605, A .802, B/T .592."""
    c = formulas.ge_coefficients(0.592)
    assert c['goal'] == pytest.approx(0.605, abs=0.001)
    assert c['assist'] == pytest.approx(0.803, abs=0.001)
    assert c['block'] == c['turn'] == 0.592


@pytest.mark.parametrize('se', [0.4, 0.6, 0.8])
def test_offence_adds_up_to_goals(se):
    """However many turns, a team's goals and assists less its turns are
    worth its goals: with SE = goals / (goals + turns)."""
    goals = 30
    turns = goals * (1 - se) / se
    ge = formulas.goal_equivalents({'goals': goals, 'assists': goals, 'turnovers': turns}, se)
    assert ge['total'] == pytest.approx(goals)


def test_scoring_efficiency():
    assert formulas.scoring_efficiency(15, 10) == pytest.approx(0.6)
    assert formulas.scoring_efficiency(0, 0) == formulas.DEFAULT_SE


@pytest.mark.parametrize('offence, scored, events, ok', [
    (True, True, ['catch', 'goal'], True),                                   # clean hold
    (True, True, ['throwaway', 'block', 'goal'], True),                      # hold after a turn
    (True, False, ['drop', 'scored_on'], True),                              # broken
    (True, False, ['scored_on'], False),                                     # broken, no turn
    (False, True, ['unforced_turnover', 'catch', 'goal'], True),             # break
    (False, True, ['callahan'], True),
    (False, True, ['catch', 'goal'], False),                                 # break, no regain
    (False, False, ['scored_on'], True),
    (False, False, ['block', 'scored_on'], False),                           # regained, never lost
    (False, True, ['block', 'throwaway', 'forced_turnover', 'goal'], True),
])
def test_possession_gap(offence, scored, events, ok):
    assert (formulas.possession_gap(offence, scored, events) is None) == ok


def test_goal_equivalents_by_hand():
    se = 0.5
    ge = formulas.goal_equivalents(BASE, se)
    plus = 2 * (0.86 - 0.43 * se) + 3 * (1.14 - 0.57 * se) + 1 * se
    assert ge['gab'] == pytest.approx(plus)
    assert ge['turns'] == pytest.approx(0.5)
    assert ge['total'] == pytest.approx(plus - 0.5)
    # A Callahan is a goal and a block
    cal = formulas.goal_equivalents({'callahans': 1}, se)
    assert cal['total'] == pytest.approx((0.86 - 0.43 * se) + se)


def test_per_is_team_rate_for_an_average_player_and_shrinks_small_samples():
    se = 0.5
    rate = formulas.goal_equivalents(BASE, se)['total'] / 10
    team_avgs = {'se': se, 'avg_ge_per_point': rate}
    assert formulas.calculate_per(BASE, team_avgs) == pytest.approx(formulas.PER_SCALE * rate)
    # Same rate, different sample: same PER (no volume penalty)
    double = {k: v * 2 if isinstance(v, int) else v for k, v in BASE.items()}
    assert formulas.calculate_per(double, team_avgs) == pytest.approx(formulas.PER_SCALE * rate)
    # One great point is pulled most of the way back to the team
    hot = {'points_played': 1, 'goals': 1, 'assists': 1}
    hot_rate = formulas.goal_equivalents(hot, se)['total']
    assert formulas.PER_SCALE * rate < formulas.calculate_per(hot, team_avgs) < formulas.PER_SCALE * hot_rate / 2
    assert formulas.calculate_per({**BASE, 'points_played': 0}, team_avgs) == 0


def test_eff_rewards_not_giving_it_back():
    team_avgs = {'se': 0.6, 'eff_prior': 1.0}
    clean = formulas.calculate_eff({'goals': 3, 'assists': 3}, team_avgs)
    loose = formulas.calculate_eff({'goals': 3, 'assists': 3, 'turnovers': 4}, team_avgs)
    assert 0 < loose < clean < 1
    assert formulas.calculate_eff({'turnovers': 2}, team_avgs) == 0
    # The prior keeps one goal and no turns from beating a big clean line
    assert formulas.calculate_eff({'goals': 1}, team_avgs) < clean


def test_apply_ratings_fills_every_rating():
    stats = formulas.apply_ratings(dict(BASE), {'se': 0.6, 'avg_ge_per_point': 0.2, 'eff_prior': 1.0})
    for key in ('per', 'eff', 'epm', 'ge_plus', 'ge_turns'):
        assert key in stats
    assert stats['epm'] == pytest.approx(stats['ge_plus'] - stats['ge_turns'])


def test_line_efficiency_ranks_by_conversion():
    class P:
        def __init__(self, pid):
            self.id = pid
    a, b, c = P(1), P(2), P(3)
    stats = {1: {'o_line_points_played': 4, 'o_line_points_scored': 2},
             2: {'o_line_points_played': 4, 'o_line_points_scored': 3},
             3: {'o_line_points_played': 0, 'o_line_points_scored': 0}}
    ranked = formulas.calculate_optimized_line_efficiency([a, b, c], stats, is_offensive=True, min_points=1)
    assert ranked == [(b, 0.75), (a, 0.5)]
    # One point at 100% isn't the best O-line player: too few points to rank
    stats[3] = {'o_line_points_played': 1, 'o_line_points_scored': 1}
    assert formulas.calculate_optimized_line_efficiency([a, b, c], stats, is_offensive=True, min_points=4) == [(b, 0.75), (a, 0.5)]


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


def test_ratings_page_explains_with_the_teams_numbers(app, season):
    from app.stats.team import calculate_scoring_efficiency
    with app.test_request_context():
        from flask_login import login_user
        from app.models.user import User
        login_user(User.query.first())
        se = calculate_scoring_efficiency(None)
    assert se['se_goals'] > 0
    assert se['se'] == pytest.approx(se['se_goals'] / (se['se_goals'] + se['se_turns']))
    html = season['client'].get('/stats/ratings').get_data(as_text=True)
    assert 'Scoring efficiency (SE)' in html
    assert '%.3f' % se['se'] in html
    assert 'A worked example' in html and 'Once points are recorded' not in html
    assert "Points that don't add up" in html


def test_incomplete_points_are_found_and_left_out_of_se(app, season):
    from flask_login import login_user
    from app.models.event import Event
    from app.models.point import Point
    from app.models.user import User
    from app.stats.team import calculate_scoring_efficiency, find_incomplete_points
    with app.test_request_context():
        login_user(User.query.first())
        before = calculate_scoring_efficiency(None)
        assert find_incomplete_points(None) == []
        # Wipe the turns from a point we broke: it can't add up any more
        point = next(p for p in Point.query.all()
                     if p.point_outcome == 'scored' and p.our_line_type == 'D-line'
                     and any(e.event_type == 'goal' for e in p.events))
        for e in list(point.events):
            if e.event_type in formulas.POSSESSION_CHANGES:
                db.session.delete(e)
        db.session.commit()
        point_id = point.id
        cache.clear()
        db.session.remove()  # a new request: games forget their loaded points
    with app.test_request_context():
        login_user(User.query.first())
        found = find_incomplete_points(None)
        after = calculate_scoring_efficiency(None)
    assert [p['point_id'] for p in found] == [point_id]
    assert 'no block or turnover' in found[0]['reason']
    assert after['se_incomplete'] == 1
    assert after['se_goals'] == before['se_goals'] - 1
    html = season['client'].get('/stats/ratings').get_data(as_text=True)
    assert f'/points/{point_id}' in html


def test_dashboard_shows_epm_and_eff(app, season):
    html = season['client'].get('/stats/').get_data(as_text=True)
    assert '>EPM<' in html and '>Eff<' in html
    assert '/stats/ratings' in html


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


def test_percentile_counts_ties_half_and_can_be_inverted():
    from app.stats.profile import percentile
    assert percentile(5, [1, 5, 9]) == pytest.approx(50)
    assert percentile(9, [1, 5, 9]) == pytest.approx(100 * 2.5 / 3)
    # Fewer turnovers ranks higher
    assert percentile(1, [1, 5, 9], lower_better=True) == pytest.approx(100 * 2.5 / 3)


def test_radar_profile_ranks_against_teammates(app, season):
    from flask_login import login_user
    from app.models.game import Game
    from app.models.player import Player
    from app.models.user import User
    from app.stats import turnovers
    from app.stats.formulas import apply_ratings
    from app.stats.players import get_players_base_stats
    from app.stats.profile import RADAR_AXES, radar_profile, rating_comparison
    with app.test_request_context():
        login_user(User.query.filter_by(username='admin').first())
        games = Game.query.all()
        players = Player.query.filter(Player.id.in_(season['player_ids'])).all()
        stats = get_players_base_stats(players, games)
        for s in stats.values():
            apply_ratings(s, {})
        pid = season['player_ids'][0]
        profile = radar_profile(pid, stats, turnovers.ThrowingData(games), {g.id for g in games})
        ratings = rating_comparison(pid, stats)
    for side, axes in RADAR_AXES.items():
        assert [a['key'] for a in profile[side]] == [a['key'] for a in axes]
        for row in profile[side]:
            assert row['percentile'] is None or 0 <= row['percentile'] <= 100
    # Somebody on a recorded season has a ranked completion rate
    assert profile['offence'][0]['team_median'] is not None
    assert {r['key'] for r in ratings['rows']} >= {'per', 'epm', 'eff'}


def test_player_page_shows_the_profile_radars(app, season):
    page = season['client'].get(f"/stats/player/{season['player_ids'][0]}").get_data(as_text=True)
    assert 'Offensive Profile' in page and 'Defensive Profile' in page
    assert 'const RADAR_PROFILE = {' in page
    assert 'Median teammate' in page
    # The old fixed "elite" scales and the team-total comparison are gone
    assert 'Elite benchmarks' not in page and 'Team Average' not in page
    assert 'Profile vs Teammates' in page    # in the printable report too


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
