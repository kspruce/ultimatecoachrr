"""Points taken live on Game Day next to points with full stats: per-point
rates only count full-stat points, the season box score counts every point
once, pulls come from Game Day, and games show what's left to analyse."""
from app import db
from app.models.point import Point
from tests.test_point_setup import _line, _save, setup  # noqa: F401


def _gameday_point(setup, number, line, events, outcome='scored'):
    r = setup['client'].post('/gameday/api/record-point', json={
        'game_id': setup['game_id'], 'point_number': number, 'line_type': 'O-line',
        'gender_ratio': '4-3', 'players': line, 'events': events, 'outcome': outcome})
    assert r.get_json()['success'], r.get_data(as_text=True)


def _full_point(setup, plays):
    _save(setup, _line())
    point = Point.query.filter_by(game_id=setup['game_id']).order_by(Point.point_number.desc()).first()
    for pid, event, x in plays:
        r = setup['client'].post(f'/stats/record/{point.id}', json={
            'player_id': str(pid), 'event_type': event, 'field_position_x': x,
            'field_position_y': 18, 'is_offensive': True})
        assert r.status_code == 201, r.get_data(as_text=True)
    setup['client'].post(f'/stats/finish_point/{point.id}')
    return point.id


def _stats(app, setup, player_ids):
    from flask_login import login_user
    from app.models.game import Game
    from app.models.player import Player
    from app.models.user import User
    from app.stats.players import get_players_base_stats
    with app.test_request_context():
        login_user(User.query.first())
        from flask import session
        session['current_team_id'] = setup['team_id']
        players = Player.query.filter(Player.id.in_(player_ids)).all()
        return get_players_base_stats(players, Game.query.all())


def _season(setup):
    a, b, c, d = _line()[:4]
    _gameday_point(setup, 1, _line(), [
        {'type': 'pull', 'player_id': a, 'result': 'in', 'hang_time': 4.5},
        {'type': 'assist', 'player_id': c},
        {'type': 'score', 'player_id': b},
        {'type': 'throwaway', 'player_id': d},
    ])
    full_id = _full_point(setup, [(a, 'catch', 30), (b, 'catch', 45), (c, 'goal', 95)])
    return a, b, c, d, full_id


def test_per_point_rates_only_count_points_with_full_stats(app, setup):
    a, b, c, d, _ = _season(setup)
    stats = _stats(app, setup, [a, b, c])
    for pid in (a, b, c):
        assert stats[pid]['points_played'] == 2
        assert stats[pid]['analysed_points'] == 1
        assert stats[pid]['gameday_only_points'] == 1
        assert stats[pid]['o_line_points_played'] == 2      # results: every point
        assert stats[pid]['o_line_conversion_rate'] == 100
    # c's one goal came on c's one point with full stats
    r = setup['client'].get('/stats/team/export.csv').get_data(as_text=True)
    import csv, io  # noqa: E401
    rows = {row['name']: row for row in csv.DictReader(io.StringIO(r))}
    from app.models.player import Player
    row = rows[db.session.get(Player, c).name]
    assert float(row['goals_per_point']) == 1.0
    assert row['points_with_full_stats'] == '1' and row['points_played'] == '2'


def test_box_score_counts_every_point_once(app, setup):
    a, b, c, d, full_id = _season(setup)
    stats = _stats(app, setup, [a, b, c, d])
    assert stats[b]['box']['goals'] == 1       # the Game Day goal
    assert stats[c]['box']['goals'] == 1       # the full-stats goal
    assert stats[c]['box']['assists'] == 1     # the Game Day assist
    assert stats[d]['box']['turnovers'] == 1
    assert stats[b]['goals'] == 0              # event stats: full stats only

    # Once the Game Day point gets full stats, those replace its Game Day record
    gameday_point = Point.query.filter_by(game_id=setup['game_id'], point_number=1).one()
    setup['client'].post(f'/stats/record/{gameday_point.id}', json={
        'player_id': str(a), 'event_type': 'catch', 'field_position_x': 30,
        'field_position_y': 18, 'is_offensive': True})
    stats = _stats(app, setup, [b, d])
    assert stats[b]['box']['goals'] == 0 and stats[d]['box']['turnovers'] == 0
    assert stats[b]['analysed_points'] == 2


def test_pulls_come_from_game_day(app, setup):
    a, *_ = _season(setup)
    pulls = _stats(app, setup, [a])[a]['pulls']
    assert pulls['pulls'] == 1 and pulls['out'] == 0 and pulls['avg_hang_time'] == 4.5


def test_game_day_points_are_not_clean_holds(app, setup):
    _season(setup)
    from flask_login import login_user
    from app.models.game import Game
    from app.models.user import User
    from app.stats.team import calculate_possession_based_team_metrics
    with app.test_request_context():
        login_user(User.query.first())
        metrics = calculate_possession_based_team_metrics(Game.query.all())
    assert metrics['clean_hold_percentage'] == 100   # 1 of the 1 point with full stats


def test_pages_say_what_has_full_stats(app, setup):
    a, b, *_ = _season(setup)
    client = setup['client']
    page = client.get(f'/stats/player/{b}').get_data(as_text=True)
    assert 'Full stats from <strong>1 of 2</strong>' in page
    assert 'Season Box Score' in page
    game_page = client.get(f"/games/{setup['game_id']}").get_data(as_text=True)
    assert 'waiting for full stats' in game_page and 'Analyse point 1' in game_page
    points_page = client.get(f"/points/game/{setup['game_id']}").get_data(as_text=True)
    assert 'Game Day only' in points_page
    pull_page = client.get(f'/stats/player/{a}').get_data(as_text=True)
    assert 'Average hang time' in pull_page
    assert client.get('/stats/team').status_code == 200
    assert 'Full stats from <strong>1 of 2</strong>' in client.get('/stats/team').get_data(as_text=True)
    assert client.get(f"/stats/game/{setup['game_id']}").status_code == 200


def test_analysis_progress(app, setup):
    _season(setup)
    from app.models.game import Game
    from app.utils.point_flow import analysis_progress
    from flask_login import login_user
    from app.models.user import User
    with app.test_request_context():
        login_user(User.query.first())
        progress = analysis_progress(db.session.get(Game, setup['game_id']))
    assert progress['total'] == 2 and progress['waiting'] == 1
    assert progress['next'].point_number == 1
